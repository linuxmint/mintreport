# Mintreport

This is a troubleshooting tool to analyse crash reports and browse through important information.

# Note to developers

The glade file contains Gtk.Stack widgets so it cannot be opened with Glade 3.18.

In Mint 18.x, you can get Glade 3.20 via Flatpak.

```
sudo add-apt-repository ppa:alexlarsson/flatpak
sudo apt update && sudo apt install flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.gnome.Glade
flatpak run org.gnome.Glade
```
