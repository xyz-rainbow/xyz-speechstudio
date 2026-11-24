# ⚡ XYZ-Productions: Modular Inno Setup Installer Template

> **Plantilla Modular de Instalador Cyberpunk / Scene Keygen para Windows (x64)**  
> Compatible con Windows 10 y Windows 11. Diseñado para distribución profesional, soporte portable autónomo, compresión ultra LZMA2 y estética visual de alto impacto.

---

## 🎨 Características Visuales y Funcionales

* **Estética Cyberpunk & Modern Squircle**:
  * **Header superior Dark Cyber** (`#0E1016`) con corte inferior en **Rosa Neón** (`#FF10F0`).
  * **Icono de cabecera** centrado verticalmente en la esquina superior derecha.
  * **Contador dinámico de pasos** (`[ PASO 1/5 ]` al `[ PASO 5/5 ]`) en tipografía monospace `Consolas` y **Verde Lima** (`#39FF14`).
  * **Barra de instalación en Verde Lima** con fondo oscuro acentuado vía Win32 Nativo (`uxtheme.dll` y `SendMessage`).
  * **Bordes en Rosa Neón** alrededor de todos los botones (`Atrás`, `Siguiente`, `Cancelar`, `Examinar`), cajas de texto, memos y barra de progreso.
* **100% Modular**:
  * Toda la personalización se realiza en un único archivo: [`config.iss`](config.iss). No requieres editar código Pascal ni Delphi.
* **Destino de Speech Studio**:
  * La ruta por defecto es `%ProgramFiles%\XYZ-Productions\Speech Studio`. No instala en `%LOCALAPPDATA%`.
  * El modo portable sigue disponible y no deja clave de desinstalación.
* **Compresión Ultra LZMA2**:
  * Diccionario de 1024 MB en proceso independiente para máxima densidad de empaquetado.
* **Bilingüe Nativo (ES / EN)**:
  * Selector de idioma al inicio con contratos de licencia (EULA) y textos independientes para Español e Inglés.

---

## 📁 Estructura del Proyecto

```text
XYZ-Installer-Template/
├── config.iss              <- Configuración central (Nombre, Versión, GUID, Colores, Rutas)
├── installer.iss           <- Script maestro del instalador Inno Setup
├── build.bat               <- Compilador automático 1-Click (CMD / Batch)
├── build.ps1               <- Compilador automático 1-Click (PowerShell con logs de color)
├── assets/
│   ├── app_icon.ico        <- Master ICO multi-resolución (256, 128, 64, 48, 32, 16 px)
│   ├── banner_side.bmp     <- Banner lateral vertical (164 x 314 px) con degradado y cápsula
│   ├── banner_header.bmp   <- Icono para cabecera superior (55 x 55 px)
│   ├── Icono_Original.jpg  <- Arte original de referencia (750 x 750 px)
│   └── Final_Mockup.jpg    <- Captura de la ventana final de instalación
├── texts/
│   ├── info_before.txt     <- Ficha NFO con arte ASCII centrado de XYZ-Productions
│   ├── eula_es.txt         <- Contrato de Licencia / Términos de Uso en Español
│   └── eula_en.txt         <- Contrato de Licencia / Términos de Uso en Inglés
├── app_payload/            <- Carpeta donde depositas los archivos compilados de tu app
│   └── .gitkeep
└── README.md               <- Esta documentación
```

---

## 🚀 Guía de Inicio Rápido (3 Pasos)

### 1. Depositar los archivos de tu programa
Copia los binarios y recursos de tu aplicación dentro del directorio `app_payload/`. Todo lo que pongas aquí se empaquetará recursivamente respetando subcarpetas.

### 2. Editar `config.iss`
Abre [`config.iss`](config.iss) y ajusta los valores para tu nuevo proyecto:

```iss
#define MyAppName "Mi Nueva Aplicacion"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "XYZ-Productions"
#define MyAppURL "https://github.com/tu-usuario"
#define MyAppExeName "mi-app.exe"
#define MyAppId "{{TU-NUEVO-GUID-AQUI}}"

#define MyDefaultDirName "{autopf}\XYZ-Productions\Mi Nueva Aplicacion"
#define OutputDirectory "..\Output"
#define OutputBaseFilename "MiApp_v1.0.0_Setup"
```

> **Generar un nuevo GUID**: Puedes presionar `Ctrl + Shift + G` en el IDE de Inno Setup o ejecutar en PowerShell: `[guid]::NewGuid().ToString("B").ToUpper()`.

### 3. Compilar el Instalador
Ejecuta con doble clic **`build.bat`** o ejecuta en PowerShell:
```powershell
.\build.ps1
```
El script detectará automáticamente tu instalación de Inno Setup 6 y generará el ejecutable final en la carpeta configurada.

---

## 🎨 Personalización de Colores

Los colores están definidos en formato **BGR** (`$00BBGGRR`) para Delphi / Inno Setup dentro de `config.iss`:

| Elemento | Variable | Hexadecimal | BGR Inno Setup |
| :--- | :--- | :--- | :--- |
| **Cabecera (Fondo)** | `#define ColorHeaderBg` | `#0E1016` | `"$0016100E"` |
| **Acento Neón (Marcos y líneas)** | `#define ColorNeonPink` | `#FF10F0` | `"$00F010FF"` |
| **Progreso e Indicadores** | `#define ColorLimeGreen` | `#39FF14` | `"$0014FF39"` |
| **Texto secundario / Plata** | `#define ColorTextSilver` | `#D0D0D0` | `"$00D0D0D0"` |

---

## 🛠️ Requisitos Previos

* **Windows 10 / 11 (64-bit)**
* **Inno Setup 6.2+** (Descarga gratuita desde [jrsoftware.org](https://jrsoftware.org/isdl.php))

---

## 📜 Licencia y Autoría

Desarrollado por **Rainbow Technology & XYZ-Productions**.  
Distribuido como plantilla modular reutilizable para proyectos de software autónomos.
