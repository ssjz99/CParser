#include "example.h"

struct Config app_config = {
    1,
    5,
    "debug.log",
    30,
    "application.log"
};

struct Device default_device = {
    1001,
    "sensor",
    "acme",
    2025,
    4.5f
};

struct RobotSystem myBot = {
    .name = "Alpha-Bot",
    .hw = {
        .firmware_version = 2,
        .sensor = {
            .id = 101,
            .readings = {10.5f, 20.2f, 15.8f, 30.1f, 25.4f}
        }
    },
    .grid_map = { 
        {0, 1, 0}, 
        {1, 1, 1}, 
        {0, 0, 0} 
    }
};