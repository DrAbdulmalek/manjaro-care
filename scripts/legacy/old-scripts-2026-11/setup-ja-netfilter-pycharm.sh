#!/bin/bash
# ============================================================
# Integrated script for setting up PyCharm Professional with
# ja-netfilter (educational purposes only)
# Supports Manjaro / Arch Linux
# ============================================================

set -e  # exit on error

# ------------------- Colors -------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# ------------------- Configuration -------------------
BASE_DIR="$HOME/jetbrains-tools"
JA_DIR="$BASE_DIR/ja-netfilter"        # from BadKid90s
LICENSE_FILE="$BASE_DIR/active-code.txt" # from fnwind
SERVER_DIR="$BASE_DIR/license-server"   # from Blduu (optional)
JA_JAR="$JA_DIR/ja-netfilter.jar"
CONFIG_DIR="$JA_DIR/config-jetbrains"
VMOPTIONS_DIR="$JA_DIR/vmoptions"
TARGET_VMOPTIONS_DIR="$HOME/.config/JetBrains/PyCharm2026.1"
TARGET_VMOPTIONS_FILE="$TARGET_VMOPTIONS_DIR/pycharm64.vmoptions"
PYCHARM_LAUNCHER="/usr/local/bin/pycharm"

# ------------------- Pre-checks -------------------
print_step "Checking system requirements..."

if ! command -v git &>/dev/null; then
    print_info "Installing git..."
    sudo pacman -S --needed git
fi

if ! command -v curl &>/dev/null; then
    print_info "Installing curl..."
    sudo pacman -S --needed curl
fi

if ! command -v java &>/dev/null; then
    print_warn "Java not found, ja-netfilter may still work, but license server requires Java."
fi

if [ ! -d "/opt/pycharm-2026.1" ] && [ ! -d "/opt/pycharm-professional" ]; then
    print_error "PyCharm Professional not found in /opt/pycharm-2026.1 or /opt/pycharm-professional"
    print_info "Please extract your PyCharm Pro .tar.gz to /opt/pycharm-2026.1 first."
    exit 1
fi

# ------------------- Clone / update repositories -------------------
print_step "Cloning/updating repositories..."

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# 1. ja-netfilter (BadKid90s) - core framework
if [ -d "$JA_DIR" ]; then
    print_info "Updating ja-netfilter (BadKid90s)..."
    cd "$JA_DIR" && git pull && cd ..
else
    print_info "Cloning ja-netfilter from BadKid90s..."
    git clone https://github.com/BadKid90s/ja-netfilter.git
fi

# 2. License server (Blduu) - optional
if [ -d "$SERVER_DIR" ]; then
    print_info "Updating license server (Blduu)..."
    cd "$SERVER_DIR" && git pull && cd ..
else
    print_info "Cloning license server from Blduu (optional)..."
    git clone https://github.com/Blduu/Jetbrains-LicenseServer-Help.git "$SERVER_DIR"
fi

# 3. Activation code (fnwind)
if [ ! -f "$LICENSE_FILE" ]; then
    print_info "Fetching active-code.txt from fnwind..."
    # clone only needed file
    git clone --depth 1 https://github.com/fnwind/idea-license-ja-netfilter.git /tmp/fnwind-temp
    cp /tmp/fnwind-temp/active-code.txt "$BASE_DIR/"
    rm -rf /tmp/fnwind-temp
else
    print_info "active-code.txt already exists, skipping."
fi

# ------------------- Prepare vmoptions files -------------------
print_step "Preparing vmoptions for PyCharm..."

# Create target directory
mkdir -p "$TARGET_VMOPTIONS_DIR"

# Backup existing vmoptions if any
if [ -f "$TARGET_VMOPTIONS_FILE" ]; then
    BACKUP="${TARGET_VMOPTIONS_FILE}.backup.$(date +%Y%m%d%H%M%S)"
    cp "$TARGET_VMOPTIONS_FILE" "$BACKUP"
    print_info "Backed up existing vmoptions to $BACKUP"
fi

# Write new vmoptions (combine defaults + ja-netfilter)
cat > "$TARGET_VMOPTIONS_FILE" << EOF
# PyCharm VM options with ja-netfilter (educational use)
-Xms128m
-Xmx2048m
-XX:ReservedCodeCacheSize=512m
-XX:+IgnoreUnrecognizedVMOptions
-XX:+UseG1GC
-XX:SoftRefLRUPolicyMSPerMB=50
-XX:CICompilerCount=2
-XX:+HeapDumpOnOutOfMemoryError
-XX:-OmitStackTraceInFastThrow
-ea
-Dsun.io.useCanonCaches=false
-Djdk.http.auth.tunneling.disabledSchemes=""
-Djdk.attach.allowAttachSelf=true
-Djdk.module.illegalAccess.silent=true
-Dkotlinx.coroutines.debug=off

# Java 17+ required opens
--add-opens=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED
--add-opens=java.base/jdk.internal.org.objectweb.asm.tree=ALL-UNNAMED

# ja-netfilter javaagent
-javaagent:$JA_JAR=jetbrains
EOF

print_info "VM options written to $TARGET_VMOPTIONS_FILE"

# ------------------- Set environment variable -------------------
print_step "Setting PYCHARM_VM_OPTIONS environment variable..."

SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")
EXPORT_LINE="export PYCHARM_VM_OPTIONS=\"$TARGET_VMOPTIONS_FILE\""

for config in "${SHELL_CONFIGS[@]}"; do
    if [ -f "$config" ]; then
        # remove old line if exists
        sed -i '/export PYCHARM_VM_OPTIONS=/d' "$config"
        echo "$EXPORT_LINE" >> "$config"
        print_info "Added to $config"
    fi
done

# For current session
eval "$EXPORT_LINE"
print_info "Environment variable set for current shell"

# ------------------- KDE Plasma support -------------------
if [ -d "$HOME/.config/plasma-workspace/env" ]; then
    KDE_ENV="$HOME/.config/plasma-workspace/env/pycharm-vmoptions.sh"
    echo "#!/bin/sh" > "$KDE_ENV"
    echo "$EXPORT_LINE" >> "$KDE_ENV"
    chmod +x "$KDE_ENV"
    print_info "KDE environment file created: $KDE_ENV"
fi

# ------------------- Create PyCharm launcher with fixes -------------------
print_step "Creating PyCharm launcher script..."

# Detect actual PyCharm installation path
if [ -d "/opt/pycharm-2026.1" ]; then
    PYCHARM_SCRIPT="/opt/pycharm-2026.1/bin/pycharm.sh"
elif [ -d "/opt/pycharm-professional" ]; then
    PYCHARM_SCRIPT="/opt/pycharm-professional/bin/pycharm.sh"
else
    print_error "PyCharm installation not found."
    exit 1
fi

sudo bash -c "cat > $PYCHARM_LAUNCHER" << EOF
#!/bin/bash
# PyCharm Professional launcher with ja-netfilter and graphics fixes
export SKIKO_RENDER_API=SOFTWARE
export __GLX_VENDOR_LIBRARY_NAME=mesa
export _JAVA_OPTIONS="-Dsun.java2d.opengl=false -Dsun.java2d.xrender=true -Dide.browser.jcef.gpu.disable=true -DjbScreenScale.enabled=false"
export JB_JAVA2D_FORCE_SOFTWARE=true
export PYCHARM_VM_OPTIONS="$TARGET_VMOPTIONS_FILE"
exec $PYCHARM_SCRIPT "\$@"
EOF

sudo chmod +x "$PYCHARM_LAUNCHER"
print_info "Launcher created at $PYCHARM_LAUNCHER"

# ------------------- Desktop shortcut -------------------
print_step "Creating desktop shortcut..."

DESKTOP_FILE="$HOME/Desktop/PyCharm-ja.desktop"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=PyCharm Pro (ja-netfilter)
Comment=Python IDE - Educational configuration
Exec=$PYCHARM_LAUNCHER %F
Icon=/opt/pycharm-2026.1/bin/pycharm.png
Terminal=false
Categories=Development;IDE;Python;
StartupNotify=true
StartupWMClass=jetbrains-pycharm
EOF

chmod +x "$DESKTOP_FILE"
print_info "Desktop shortcut created at $DESKTOP_FILE"

# ------------------- Instructions -------------------
echo ""
print_info "============================================"
print_info "Setup completed successfully!"
print_info "============================================"
echo ""
print_info "📌 Next steps:"
echo "  1. Restart your shell or run: source ~/.bashrc (or ~/.zshrc)"
echo "  2. Launch PyCharm via terminal: pycharm"
echo "     or double-click the desktop shortcut."
echo ""
print_info "🔑 Activation options (choose one):"
echo "  A) Use activation code from: $LICENSE_FILE"
echo "     Open PyCharm -> Help -> Register -> Activation code"
echo "     Copy the entire content of that file."
echo ""
echo "  B) Use local license server (if code fails):"
echo "     cd $SERVER_DIR"
echo "     java -jar Jetbrains-LicenseServer-Help.jar"
echo "     Then in PyCharm: License server -> http://localhost:8080"
echo ""
print_warn "⚠️  Note: This is for educational purposes only."
print_warn "   If you use JetBrains products professionally, please buy a license."
echo ""

# ------------------- Verify ja-netfilter config -------------------
print_step "Verifying ja-netfilter configuration..."

if [ -f "$JA_JAR" ]; then
    print_info "ja-netfilter.jar found at $JA_JAR"
else
    print_error "ja-netfilter.jar not found! Check the clone from BadKid90s."
    exit 1
fi

if [ -f "$CONFIG_DIR/url.conf" ]; then
    print_info "url.conf exists (you may edit rules in $CONFIG_DIR)"
else
    print_warn "url.conf not found, creating basic one..."
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/url.conf" << 'EOC'
[URL]
PREFIX,https://account.jetbrains.com/lservice/rpc/validateKey.action
EQUAL,https://jetbrains.com/
EOC
fi

print_info "All done! Enjoy your educational environment."
