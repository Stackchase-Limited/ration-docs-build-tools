# Vendored plugin API (sdkjs-plugins/v1)

`v1/plugins.js`, `v1/plugins-ui.js` and `v1/plugins.css` are the plugin-side API that
every editor plugin loads, including our own desktop-sdk plugins (encryption, Send to).
They come from ONLYOFFICE's `onlyoffice.github.io` repository at
`4fb0f3dfaf33c3f1e3d9662d17f4245e617a3d47`, the commit the macOS 9.4 build shipped
(`locks/onlyoffice-desktop-9.4.0.lock`), unmodified and under its AGPL-3.0 licence.

build_tools used to download them from https://onlyoffice.github.io at every deploy.
Ration Docs builds only from our own repositories, so the deploy copies these instead
(`base.copy_plugins_api`). To update them, replace the three files from a newer commit
and record it here.
