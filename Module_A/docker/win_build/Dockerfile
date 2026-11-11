# Builds the Windows .exe of BRICS Mission Studio on a Mac/Linux host (Wine + Windows Python 3.11 + PyInstaller).
# Wheels are downloaded on the host first (build/wheels_winbuild) - pip under Wine is too slow for the network.
FROM --platform=linux/amd64 tobix/pywine:3.11
COPY wheels /wheels
RUN wine python -m pip install --no-index --find-links Z:\\wheels pyinstaller PySide6 pyyaml markdown pillow
WORKDIR /src
