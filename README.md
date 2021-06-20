# Mintreport

This is a troubleshooting tool to analyse crash reports and browse through important information.

![image](https://user-images.githubusercontent.com/19881231/122669008-e114d980-d1c3-11eb-928d-905684286545.png)

## Build
Get source code
```
git clone https://github.com/linuxmint/mintreport
cd mintreport
```
Build
```
dpkg-buildpackage --no-sign
```
Install
```
cd ..
sudo dpkg -i mintreport*.deb
```

## Translations
Please use Launchpad to translate Mintreport: https://translations.launchpad.net/linuxmint/latest/.

The PO files in this project are imported from there.

## License
- Code: GPLv3
