module.exports = {
  title: "Mirror",
  description: "An AI powered mirror",
  icon: "icon.webp",
  menu: async (kernel) => {
    let llama_installed = await kernel.exists(__dirname, "llama.cpp")
    let app_installed = await kernel.exists(__dirname, "venv")
    let installed = llama_installed && app_installed
    if (installed) {
      let running = await kernel.running(__dirname, "start.json")
      if (running) {
        return [{
          icon: "fa-solid fa-spin fa-circle-notch",
          text: "Running"
        }, {
          icon: "fa-solid fa-desktop",
          text: "Server",
          href: "start.json",
          params: { fullscreen: true }
        }]
      } else {
        return [{
          icon: "fa-solid fa-power-off",
          text: "Launch",
          href: "start.json",
          params: { fullscreen: true, run: true }
        }]
      }
    } else {
      return [{
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.json",
        params: { run: true, fullscreen: true }
      }]
    }
  }
}
