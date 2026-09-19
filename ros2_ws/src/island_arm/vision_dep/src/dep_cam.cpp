#include <turbojpeg.h>

#include <atomic>
#include <cstring>
#include <librealsense2/rs.hpp>
#include <memory>
#include <optional>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/point_field.hpp>
#include <string>
#include <thread>
#include <vector>

class DepthCameraNode : public rclcpp::Node {
 public:
  DepthCameraNode() : Node("dep_cam") {
    RCLCPP_INFO(get_logger(), "Starting depth camera node initialization");
    declare_parameter("raw_topic", "/vision/dep/raw/compressed");
    declare_parameter("raw_image_topic", "/vision/raw");
    declare_parameter("depth_topic", "/vision/dep/depth");
    declare_parameter("cloud_topic", "/vision/dep/cloud");
    declare_parameter("grasp_cloud_topic", "/vision/cloud");
    declare_parameter("frame_id", "camera_link");
    declare_parameter("queue_size", 10);
    // Default matches vision_dep_launch.py. 1 Hz was far too slow for face + web preview.
    declare_parameter("publish_hz", 30.0);
    declare_parameter("color_width", 1920);
    declare_parameter("color_height", 1080);
    declare_parameter("depth_width", 1280);
    declare_parameter("depth_height", 720);
    declare_parameter("fps", 30);
    declare_parameter("jpeg_quality", 85);

    RCLCPP_INFO(get_logger(), "Reading camera parameters");
    raw_topic_ = get_parameter("raw_topic").as_string();
    raw_image_topic_ = get_parameter("raw_image_topic").as_string();
    depth_topic_ = get_parameter("depth_topic").as_string();
    cloud_topic_ = get_parameter("cloud_topic").as_string();
    grasp_cloud_topic_ = get_parameter("grasp_cloud_topic").as_string();
    frame_id_ = get_parameter("frame_id").as_string();
    queue_size_ = static_cast<int>(get_parameter("queue_size").as_int());
    publish_hz_ = get_parameter("publish_hz").as_double();
    if (publish_hz_ <= 0.0) {
      publish_hz_ = 24.0;
    }
    publish_period_ = 1.0 / publish_hz_;
    color_width_ = static_cast<int>(get_parameter("color_width").as_int());
    color_height_ = static_cast<int>(get_parameter("color_height").as_int());
    depth_width_ = static_cast<int>(get_parameter("depth_width").as_int());
    depth_height_ = static_cast<int>(get_parameter("depth_height").as_int());
    fps_ = static_cast<int>(get_parameter("fps").as_int());
    jpeg_quality_ = static_cast<int>(get_parameter("jpeg_quality").as_int());

    RCLCPP_INFO(get_logger(), "Initializing TurboJPEG");
    tj_handle_ = tjInitCompress();
    if (!tj_handle_) {
      RCLCPP_ERROR(get_logger(), "Failed to initialize TurboJPEG compressor");
      throw std::runtime_error("TurboJPEG init failed");
    }

    RCLCPP_INFO(get_logger(), "Creating ROS publishers");
    raw_pub_ = create_publisher<sensor_msgs::msg::CompressedImage>(raw_topic_, queue_size_);
    raw_image_pub_ = create_publisher<sensor_msgs::msg::Image>(raw_image_topic_, queue_size_);
    depth_pub_ = create_publisher<sensor_msgs::msg::Image>(depth_topic_, queue_size_);
    cloud_pub_ = create_publisher<sensor_msgs::msg::PointCloud2>(cloud_topic_, queue_size_);
    grasp_cloud_pub_ =
        create_publisher<sensor_msgs::msg::PointCloud2>(grasp_cloud_topic_, queue_size_);

    RCLCPP_INFO(get_logger(), "Initializing RealSense pipeline");
    init_camera();
    RCLCPP_INFO(
        get_logger(),
        "Depth camera ready: %s (jpeg) + %s (bgr8) + %s (16UC1) + %s / %s (xyzuv) at %.2f Hz",
        raw_topic_.c_str(), raw_image_topic_.c_str(), depth_topic_.c_str(), cloud_topic_.c_str(),
        grasp_cloud_topic_.c_str(), publish_hz_);
  }

  ~DepthCameraNode() override {
    try {
      if (pipeline_) {
        pipeline_->stop();
      }
      RCLCPP_INFO(get_logger(), "Camera stopped successfully");
    } catch (const std::exception &e) {
      RCLCPP_ERROR(get_logger(), "Error stopping camera: %s", e.what());
    }

    if (tj_handle_) {
      tjDestroy(tj_handle_);
      tj_handle_ = nullptr;
    }
  }

  void process_frames() {
    try {
      rs2::frameset frames = pipeline_->wait_for_frames();
      rs2::frameset aligned = align_->process(frames);

      rs2::video_frame color_frame = aligned.get_color_frame();
      rs2::depth_frame depth_frame = aligned.get_depth_frame();

      if (!color_frame || !depth_frame) {
        RCLCPP_WARN(get_logger(), "Invalid frames received");
        return;
      }

      ++frame_count_;

      const rclcpp::Time now = get_clock()->now();
      if (last_publish_time_.has_value()) {
        if ((now - *last_publish_time_).seconds() < publish_period_) {
          return;
        }
      }
      last_publish_time_ = now;
      const rclcpp::Time stamp = now;

      publish_aligned_images(color_frame, depth_frame, stamp);

      bool expected = false;
      if (cloud_busy_.compare_exchange_strong(expected, true)) {
        rs2::depth_frame dcopy = depth_frame;
        rs2::video_frame ccopy = color_frame;
        std::thread(
            [this](rs2::depth_frame df, rs2::video_frame cf, rclcpp::Time ts) {
              publish_pointcloud(df, cf, ts);
              cloud_busy_.store(false);
            },
            dcopy, ccopy, stamp)
            .detach();
      }

      ++published_count_;
      if (published_count_ % 300 == 0) {
        RCLCPP_INFO(get_logger(), "Published %u frames at %.1f Hz", published_count_, publish_hz_);
      }
    } catch (const std::exception &e) {
      RCLCPP_ERROR(get_logger(), "Error processing frames: %s", e.what());
    }
  }

 private:
  void init_camera() {
    try {
      RCLCPP_INFO(get_logger(), "Configuring RealSense streams");
      rs2::config cfg;
      cfg.enable_stream(RS2_STREAM_COLOR, color_width_, color_height_, RS2_FORMAT_BGR8, fps_);
      cfg.enable_stream(RS2_STREAM_DEPTH, depth_width_, depth_height_, RS2_FORMAT_Z16, fps_);

      RCLCPP_INFO(get_logger(), "Starting RealSense pipeline");
      pipeline_ = std::make_unique<rs2::pipeline>();
      pipeline_->start(cfg);

      align_ = std::make_unique<rs2::align>(RS2_STREAM_COLOR);

      RCLCPP_INFO(get_logger(), "Waiting for camera frames...");
      for (int i = 0; i < 30; ++i) {
        (void)pipeline_->wait_for_frames();
      }
      RCLCPP_INFO(get_logger(), "Camera initialized successfully");
    } catch (const std::exception &e) {
      RCLCPP_ERROR(get_logger(), "Failed to initialize camera: %s", e.what());
      throw;
    }
  }

  void publish_aligned_images(const rs2::video_frame &color_frame,
                              const rs2::depth_frame &depth_frame, const rclcpp::Time &stamp) {
    try {
      // Compressed RGB for rosbridge / web preview consumers.
      const int w = static_cast<int>(color_frame.get_width());
      const int h = static_cast<int>(color_frame.get_height());
      const int bpp = 3;  // BGR8

      unsigned char *jpeg_buf = nullptr;
      unsigned long jpeg_size = 0;

      int ret = tjCompress2(tj_handle_, static_cast<const unsigned char *>(color_frame.get_data()),
                            w, w * bpp, h, TJPF_BGR, &jpeg_buf, &jpeg_size, TJSAMP_420,
                            jpeg_quality_, TJFLAG_FASTDCT);

      if (ret != 0 || !jpeg_buf || jpeg_size == 0) {
        RCLCPP_WARN(get_logger(), "JPEG compression failed: %s", tjGetErrorStr());
        return;
      }

      auto rgb_compressed_msg = std::make_unique<sensor_msgs::msg::CompressedImage>();
      rgb_compressed_msg->header.stamp = stamp;
      rgb_compressed_msg->header.frame_id = frame_id_;
      rgb_compressed_msg->format = "jpeg; bgr8 compressed";
      rgb_compressed_msg->data.resize(jpeg_size);
      std::memcpy(rgb_compressed_msg->data.data(), jpeg_buf, jpeg_size);
      tjFree(jpeg_buf);
      raw_pub_->publish(std::move(rgb_compressed_msg));

      // Raw BGR image for grasping / pixel-to-point indexing.
      sensor_msgs::msg::Image rgb_msg;
      rgb_msg.header.stamp = stamp;
      rgb_msg.header.frame_id = frame_id_;
      rgb_msg.height = color_frame.get_height();
      rgb_msg.width = color_frame.get_width();
      rgb_msg.encoding = "bgr8";
      rgb_msg.is_bigendian = false;
      rgb_msg.step = rgb_msg.width * 3;
      const size_t rgb_size = rgb_msg.step * rgb_msg.height;
      rgb_msg.data.resize(rgb_size);
      std::memcpy(rgb_msg.data.data(), color_frame.get_data(), rgb_size);
      raw_image_pub_->publish(rgb_msg);

      sensor_msgs::msg::Image depth_msg;
      depth_msg.header.stamp = stamp;
      depth_msg.header.frame_id = frame_id_;
      depth_msg.height = depth_frame.get_height();
      depth_msg.width = depth_frame.get_width();
      depth_msg.encoding = "16UC1";
      depth_msg.is_bigendian = false;
      depth_msg.step = depth_msg.width * 2;
      const size_t depth_size = depth_msg.step * depth_msg.height;
      depth_msg.data.resize(depth_size);
      std::memcpy(depth_msg.data.data(), depth_frame.get_data(), depth_size);
      depth_pub_->publish(depth_msg);
    } catch (const std::exception &e) {
      RCLCPP_ERROR(get_logger(), "Error publishing aligned images: %s", e.what());
    }
  }

  void publish_pointcloud(const rs2::depth_frame &depth_frame, const rs2::video_frame &color_frame,
                          const rclcpp::Time &stamp) {
    try {
      rs2::pointcloud pc;
      rs2::points points = pc.calculate(depth_frame);
      pc.map_to(color_frame);

      const rs2::vertex *verts = points.get_vertices();
      const size_t n = points.size();
      const int img_w = depth_frame.get_width();

      // Publish x,y,z and aligned pixel indices u,v so 2D detections can map back to 3D.
      std::vector<float> xyzuv;
      xyzuv.reserve(n * 5);
      for (size_t i = 0; i < n; ++i) {
        if (verts[i].z != 0.0F) {
          const float u = static_cast<float>(i % static_cast<size_t>(img_w));
          const float v = static_cast<float>(i / static_cast<size_t>(img_w));
          xyzuv.push_back(verts[i].x);
          xyzuv.push_back(verts[i].y);
          xyzuv.push_back(verts[i].z);
          xyzuv.push_back(u);
          xyzuv.push_back(v);
        }
      }

      if (xyzuv.empty()) {
        return;
      }

      sensor_msgs::msg::PointCloud2 cloud_msg;
      cloud_msg.header.stamp = stamp;
      cloud_msg.header.frame_id = frame_id_;
      cloud_msg.height = 1;
      cloud_msg.width = static_cast<uint32_t>(xyzuv.size() / 5);
      cloud_msg.is_dense = false;
      cloud_msg.is_bigendian = false;

      sensor_msgs::msg::PointField fx;
      fx.name = "x";
      fx.offset = 0;
      fx.datatype = sensor_msgs::msg::PointField::FLOAT32;
      fx.count = 1;
      sensor_msgs::msg::PointField fy;
      fy.name = "y";
      fy.offset = 4;
      fy.datatype = sensor_msgs::msg::PointField::FLOAT32;
      fy.count = 1;
      sensor_msgs::msg::PointField fz;
      fz.name = "z";
      fz.offset = 8;
      fz.datatype = sensor_msgs::msg::PointField::FLOAT32;
      fz.count = 1;
      sensor_msgs::msg::PointField fu;
      fu.name = "u";
      fu.offset = 12;
      fu.datatype = sensor_msgs::msg::PointField::FLOAT32;
      fu.count = 1;
      sensor_msgs::msg::PointField fv;
      fv.name = "v";
      fv.offset = 16;
      fv.datatype = sensor_msgs::msg::PointField::FLOAT32;
      fv.count = 1;
      cloud_msg.fields = {fx, fy, fz, fu, fv};

      cloud_msg.point_step = 20;
      cloud_msg.row_step = cloud_msg.point_step * cloud_msg.width;
      cloud_msg.data.resize(xyzuv.size() * sizeof(float));
      std::memcpy(cloud_msg.data.data(), xyzuv.data(), cloud_msg.data.size());

      cloud_pub_->publish(cloud_msg);
      grasp_cloud_pub_->publish(cloud_msg);
    } catch (const std::exception &e) {
      RCLCPP_ERROR(get_logger(), "Error publishing point cloud: %s", e.what());
    }
  }

  std::string raw_topic_;
  std::string raw_image_topic_;
  std::string depth_topic_;
  std::string cloud_topic_;
  std::string grasp_cloud_topic_;
  std::string frame_id_;
  int queue_size_{10};
  int color_width_{1920};
  int color_height_{1080};
  int depth_width_{1280};
  int depth_height_{720};
  int fps_{30};
  int jpeg_quality_{85};
  double publish_hz_{30.0};
  double publish_period_{1.0 / 24.0};
  std::optional<rclcpp::Time> last_publish_time_;

  rclcpp::Publisher<sensor_msgs::msg::CompressedImage>::SharedPtr raw_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr raw_image_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr depth_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr cloud_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr grasp_cloud_pub_;

  std::atomic<bool> cloud_busy_{false};

  std::unique_ptr<rs2::pipeline> pipeline_;
  std::unique_ptr<rs2::align> align_;

  // TurboJPEG
  tjhandle tj_handle_{nullptr};

  uint32_t frame_count_{0};
  uint32_t published_count_{0};
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);

  try {
    auto node = std::make_shared<DepthCameraNode>();

    while (rclcpp::ok()) {
      node->process_frames();
    }
  } catch (const std::exception &e) {
    RCLCPP_ERROR(rclcpp::get_logger("dep_cam"), "Fatal: %s", e.what());
    rclcpp::shutdown();
    return 1;
  }

  rclcpp::shutdown();
  return 0;
}
