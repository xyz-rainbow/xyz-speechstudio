use nvml_wrapper::Nvml;
use serde::Serialize;

#[derive(Serialize, Clone)]
pub struct VramStatus {
    pub available: bool,
    pub gpu: String,
    pub total_mib: u64,
    pub used_mib: u64,
    pub free_mib: u64,
}

pub fn query_vram() -> VramStatus {
    let Ok(nvml) = Nvml::init() else {
        return VramStatus {
            available: false,
            gpu: "No NVIDIA GPU".to_string(),
            total_mib: 0,
            used_mib: 0,
            free_mib: 0,
        };
    };
    let Ok(dev) = nvml.device_by_index(0) else {
        return VramStatus {
            available: false,
            gpu: "No NVIDIA GPU".to_string(),
            total_mib: 0,
            used_mib: 0,
            free_mib: 0,
        };
    };
    let name = dev.name().unwrap_or_else(|_| "NVIDIA GPU".to_string());
    match dev.memory_info() {
        Ok(mem) => VramStatus {
            available: true,
            gpu: name,
            total_mib: mem.total / (1024 * 1024),
            used_mib: mem.used / (1024 * 1024),
            free_mib: mem.free / (1024 * 1024),
        },
        Err(_) => VramStatus {
            available: false,
            gpu: name,
            total_mib: 0,
            used_mib: 0,
            free_mib: 0,
        },
    }
}
