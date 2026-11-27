# Loquendo TTS 7

Loquendo TTS 7 tiene una entrada propia en Models y en Featured del Model Hub. Usa las voces Loquendo registradas mediante Windows SAPI 5, con enumeración de 32 y 64 bits. La entrada Windows SAPI 5 continúa agrupando las demás voces disponibles del sistema.

## Instalación

En la tarjeta Loquendo, pulsa **Instalar desde archivo** y selecciona un instalador `.exe` o `.msi` del motor o de una voz. El diálogo pide confirmar que cuentas con una licencia válida y revisar las condiciones originales del proveedor. Después abre el instalador de Windows. Completa su asistente y pulsa **Buscar voces**. Puedes repetir el proceso para añadir voces.

La tarjeta aparece como instalada cuando se detecta al menos una voz Loquendo. Las voces Microsoft e IVONA no hacen que se marque Loquendo como instalado. Al seleccionar este modelo, el selector de voces muestra únicamente voces Loquendo.

La integración SAPI requiere Windows. En Linux y macOS la tarjeta indica la limitación de plataforma y mantiene desactivada la instalación. El soporte nativo del SDK para otros sistemas necesita sus propios binarios e integración.

## Fuente del pack

La búsqueda realizada el 27 de noviembre de 2026 no encontró un instalador público oficial de Loquendo TTS 7 con condiciones verificables de redistribución para incluirlo en Speech Studio. La tarjeta ofrece instalar un archivo existente. Una futura descarga integrada necesita una fuente concreta y sus condiciones de distribución.

Los proyectos consultados en GitHub son integraciones que requieren el motor y las voces por separado. El README de Loquendo AI indica que las voces se instalan aparte y el de loqtts-cli requiere una instalación del SDK. [Loquendo AI](https://github.com/JAVCIF/loquendo-ai), [loqtts-cli](https://github.com/emilysoft/loqtts-cli), [tts7-balcon-api](https://github.com/JAVCIF/tts7-balcon-api), [loquendo-tts-server](https://github.com/depau/loquendo-tts-server).

La documentación actual de Nuance Vocalizer describe compra de idiomas y voces y configuración de licencias para ese producto. [Idiomas y voces](https://docs.nuance.com/nuance-vocalizer-for-enterprise/voc-dev/ww-langs-voices.html), [Licencias](https://docs.nuance.com/nuance-vocalizer-for-enterprise/voc-install/vocig-lic.html).
