struct Config {
    int version;
#ifdef DEBUG_MODE
    int debug_level;
    char debug_file[256];
#endif
    int timeout;
#ifdef ENABLE_LOGGING
    char log_file[256];
#endif
};

struct Device {
    int device_id;
    char device_name[100];
#ifdef ENABLE_DEVICE_EXTENDED
    char manufacturer[50];
    int year_released;
    float battery_capacity;
#endif
};

struct SensorData {
    int id;
    #ifdef SENSOR_READINGS_ENABLED
    float readings[5];          // 1D field
    #endif
};

struct HardwareProfile {
    int firmware_version;
    struct SensorData sensor;   // Second layer
};

struct RobotSystem {
    char name[20];
    struct HardwareProfile hw;  // Third layer
    int grid_map[3][3];         // 2D field
};