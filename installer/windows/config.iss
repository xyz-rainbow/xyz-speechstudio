; ==============================================================================
;  XYZ-PRODUCTIONS - MODULAR INSTALLER TEMPLATE
;  Archivo de Configuración Global (config.iss)
; ==============================================================================
;  Modifica únicamente estas directivas para personalizar el instalador
;  para cualquier nuevo proyecto o aplicación en segundos.
; ==============================================================================

; --- 1. DATOS DE LA APLICACIÓN ---
#define MyAppName "Speech Studio"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Rainbow Technology & XYZ-Productions"
#define MyAppURL "https://github.com/xyz-rainbow/xyz-speechstudio"
#define MyAppExeName "speech-studio.exe"
#define MyAppId "{{7E2A9C41-5B18-4F0D-A6E3-9D4C1B8F02A7}"

; --- 2. RUTAS Y DIRECTORIOS ---
; Archivos de programa. No usa %LOCALAPPDATA%.
#define MyDefaultDirName "{autopf}\XYZ-Productions\Speech Studio"
#define MyDefaultGroupName "XYZ-Productions\Speech Studio"
#define OutputDirectory "..\Output"
#define OutputBaseFilename "SpeechStudio_0.1.0_Setup"

; --- 3. RECURSOS GRÁFICOS Y TEXTOS ---
#define SetupIconPath "assets\app_icon.ico"
#define SideBannerPath "assets\banner_side.bmp"
#define HeaderIconPath "assets\banner_header.bmp"
#define InfoBeforePath "texts\info_before.txt"
#define LicenseEsPath "texts\eula_es.txt"
#define LicenseEnPath "texts\eula_en.txt"

; --- 4. PALETA DE COLORES CYBERPUNK (Formato BGR: $00BBGGRR para Inno Setup) ---
; Fondo oscuro de la cabecera (RGB: 14, 16, 22 -> Hex: #0E1016)
#define ColorHeaderBg "$0016100E"

; Acento Rosa Neón para marcos, bordes y líneas (RGB: 255, 16, 240 -> Hex: #FF10F0)
#define ColorNeonPink "$00F010FF"

; Acento Verde Lima para barra de progreso y pasos (RGB: 57, 255, 20 -> Hex: #39FF14)
#define ColorLimeGreen "$0014FF39"

; Tono secundario para textos y descripciones
#define ColorTextSilver "$00D0D0D0"

; Fondo oscuro para la barra de progreso
#define ColorProgressBg "$00181512"
