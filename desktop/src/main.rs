#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[tauri::command]
fn pin_on_top(window: tauri::Window, value: bool) -> Result<(), String> {
    window.set_always_on_top(value).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![pin_on_top])
        .run(tauri::generate_context!())
        .expect("error while running Vector");
}
