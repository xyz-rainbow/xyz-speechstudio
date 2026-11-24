; ==============================================================================
;  XYZ-PRODUCTIONS - MODULAR MASTER INSTALLER SCRIPT
; ==============================================================================
;  Este script importa automáticamente la configuración desde 'config.iss'.
;  Incluye estética Cyberpunk/Scene, selector de ámbito (Usuario/Todos),
;  modo portable 100% limpio, cabecera con contador dinámico de pasos,
;  barra de progreso en verde lima y marcos en rosa neón.
; ==============================================================================

#include "config.iss"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={#MyDefaultDirName}
DefaultGroupName={#MyDefaultGroupName}
AllowNoIcons=yes
DisableDirPage=no
UsePreviousAppDir=no
DisableProgramGroupPage=yes

OutputDir={#OutputDirectory}
OutputBaseFilename={#OutputBaseFilename}

Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=1048576

WizardStyle=modern
WizardImageFile={#SideBannerPath}
WizardSmallImageFile={#HeaderIconPath}
SetupIconFile={#SetupIconPath}
UninstallDisplayIcon={app}\speech-studio.ico

ShowLanguageDialog=yes
UsePreviousLanguage=no

InfoBeforeFile={#InfoBeforePath}
LicenseFile={#LicenseEsPath}

PrivilegesRequired=admin

Uninstallable=yes
CreateUninstallRegKey=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"; LicenseFile: "{#LicenseEsPath}"
Name: "en"; MessagesFile: "compiler:Default.isl"; LicenseFile: "{#LicenseEnPath}"

[CustomMessages]
es.NfoTitle=Información de la Release
es.NfoSubTitle=Detalles del paquete y especificaciones internas.
en.NfoTitle=Release Information
en.NfoSubTitle=Package details and internal specifications.

es.Step1Title=[ PASO 1/5 ]  INFORMACIÓN DE LA RELEASE
es.Step1SubTitle=Especificaciones técnicas, notas del paquete y changelog interno.
en.Step1Title=[ STEP 1/5 ]  RELEASE INFORMATION
en.Step1SubTitle=Technical specifications, package notes and internal changelog.

es.Step2Title=[ PASO 2/5 ]  ACUERDO DE LICENCIA (EULA)
es.Step2SubTitle=Revise los términos de uso confidencial y no distribución.
en.Step2Title=[ STEP 2/5 ]  LICENSE AGREEMENT (EULA)
en.Step2SubTitle=Review confidential terms of use and non-distribution clauses.

es.Step3Title=[ PASO 3/5 ]  RUTA Y MODO DE INSTALACIÓN
es.Step3SubTitle=La instalación queda en Archivos de programa. El modo portable es opcional.
en.Step3Title=[ STEP 3/5 ]  DESTINATION & INSTALL MODE
en.Step3SubTitle=Setup installs under Program Files. Portable mode is optional.

es.Step4Title=[ PASO 4/5 ]  LISTO PARA INSTALAR
es.Step4SubTitle=Configuración preparada. Haga clic en Instalar para continuar.
en.Step4Title=[ STEP 4/5 ]  READY TO INSTALL
en.Step4SubTitle=Setup is ready. Click Install to begin file deployment.

es.Step5Title=[ PASO 5/5 ]  INSTALACIÓN EN PROGRESO
es.Step5SubTitle=Desplegando binarios, archivos de programa y dependencias...
en.Step5Title=[ STEP 5/5 ]  INSTALLATION IN PROGRESS
en.Step5SubTitle=Deploying binaries, program files and runtime dependencies...

es.CreateDesktopIcon=Crear acceso directo en el Escritorio con icono oficial
en.CreateDesktopIcon=Create Desktop shortcut with official icon
es.LaunchApp=Iniciar {#MyAppName}
en.LaunchApp=Launch {#MyAppName}
es.UserInstallCaption=Solo para mí (usuario actual - recomendado)
en.UserInstallCaption=Only for me (current user - recommended)
es.AllUsersInstallCaption=Instalar en Archivos de programa (todos los usuarios)
en.AllUsersInstallCaption=Install under Program Files (all users)
es.PortableCheckboxCaption=Modo Portable (crear carpeta autónoma sin registrar en Windows)
en.PortableCheckboxCaption=Portable Mode (standalone folder, no Windows registry keys)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Check: NotPortable

[Files]
; Carga automática de todos los archivos y subcarpetas dentro de app_payload
Source: "app_payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Icono del asistente, copiado junto a la app
Source: "{#SetupIconPath}"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\data\models"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\data\profiles"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\data\outputs"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\data\tmp"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{app}\.venvs"; Permissions: users-modify
Name: "{app}\runtime"; Permissions: users-modify
Name: "{app}\runtime\envs"; Permissions: users-modify
Name: "{app}\runtime\bin"; Permissions: users-modify
Name: "{app}\runtime\bin\cuda"; Permissions: users-modify
Name: "{app}\runtime\bin\cpu"; Permissions: users-modify

[Icons]
Name: "{commonprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\speech-studio.ico"; Check: IsAllUsers
Name: "{commonprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; Check: IsAllUsers
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\speech-studio.ico"; Tasks: desktopicon; Check: IsAllUsers
Name: "{app}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\speech-studio.ico"; Check: IsPortable

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\setup-env.ps1"" -AppRoot ""{app}"""; StatusMsg: "Preparando entornos Python (core, qwen, stt)..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Code]
function SetWindowTheme(hWnd: HWND; pszSubAppName: String; pszSubIdList: String): LongInt;
  external 'SetWindowTheme@uxtheme.dll stdcall';
function SendMessage(hWnd: HWND; Msg: Cardinal; wParam: LongInt; lParam: LongInt): LongInt;
  external 'SendMessageW@user32.dll stdcall';

var
  UserInstallRadio: TRadioButton;
  AllUsersRadio: TRadioButton;
  PortableCheckBox: TCheckBox;
  BackBorderPanel: TPanel;
  NextBorderPanel: TPanel;
  CancelBorderPanel: TPanel;
  BrowseBorderPanel: TPanel;
  InfoBeforeBorder: TPanel;
  LicenseBorder: TPanel;
  DirEditBorder: TPanel;
  ProgressBorder: TPanel;
  HeaderLine: TPanel;
  BottomLine: TPanel;

function IsPortable(): Boolean;
begin
  Result := (PortableCheckBox <> nil) and PortableCheckBox.Checked;
end;

function IsAllUsers(): Boolean;
begin
  Result := (AllUsersRadio <> nil) and AllUsersRadio.Checked and not IsPortable();
end;

function IsCurrentUser(): Boolean;
begin
  Result := (UserInstallRadio <> nil) and UserInstallRadio.Checked and not IsPortable();
end;

function NotPortable(): Boolean;
begin
  Result := not IsPortable();
end;

procedure OnScopeChange(Sender: TObject);
begin
  if PortableCheckBox.Checked then
  begin
    if UserInstallRadio <> nil then
      UserInstallRadio.Enabled := False;
    AllUsersRadio.Enabled := False;
  end
  else
  begin
    if UserInstallRadio <> nil then
      UserInstallRadio.Enabled := True;
    AllUsersRadio.Enabled := True;
    AllUsersRadio.Checked := True;
    WizardForm.DirEdit.Text := ExpandConstant('{#MyDefaultDirName}');
  end;
end;

function CreateNeonBorder(TargetControl: TControl): TPanel;
var
  Border: TPanel;
begin
  Border := TPanel.Create(WizardForm);
  Border.Parent := TargetControl.Parent;
  Border.SetBounds(
    TargetControl.Left - ScaleX(1),
    TargetControl.Top - ScaleY(1),
    TargetControl.Width + ScaleX(2),
    TargetControl.Height + ScaleY(2)
  );
  Border.Color := {#ColorNeonPink};
  Border.BevelOuter := bvNone;
  TargetControl.BringToFront;
  Result := Border;
end;

procedure InitializeWizard();
begin
  // 1. Cabecera personalizada Dark Cyber
  WizardForm.MainPanel.ParentBackground := False;
  WizardForm.MainPanel.Color := {#ColorHeaderBg};

  // Franja divisoria en Rosa Neón
  HeaderLine := TPanel.Create(WizardForm);
  HeaderLine.Parent := WizardForm.MainPanel;
  HeaderLine.Left := 0;
  HeaderLine.Top := WizardForm.MainPanel.Height - ScaleY(2);
  HeaderLine.Width := WizardForm.MainPanel.Width;
  HeaderLine.Height := ScaleY(2);
  HeaderLine.Color := {#ColorNeonPink};
  HeaderLine.BevelOuter := bvNone;

  // Icono superior derecho centrado verticalmente
  WizardForm.WizardSmallBitmapImage.Top := (WizardForm.MainPanel.Height - WizardForm.WizardSmallBitmapImage.Height) div 2;
  WizardForm.WizardSmallBitmapImage.Left := WizardForm.MainPanel.ClientWidth - WizardForm.WizardSmallBitmapImage.Width - ScaleX(16);

  // Contador de pasos en la cabecera (Arriba a la izquierda)
  WizardForm.PageNameLabel.Left := ScaleX(16);
  WizardForm.PageNameLabel.Top := ScaleY(10);
  WizardForm.PageNameLabel.Width := WizardForm.WizardSmallBitmapImage.Left - WizardForm.PageNameLabel.Left - ScaleX(8);
  WizardForm.PageNameLabel.Font.Name := 'Consolas';
  WizardForm.PageNameLabel.Font.Style := [fsBold];
  WizardForm.PageNameLabel.Font.Size := 9;
  WizardForm.PageNameLabel.Font.Color := {#ColorLimeGreen};

  WizardForm.PageDescriptionLabel.Left := ScaleX(16);
  WizardForm.PageDescriptionLabel.Top := WizardForm.PageNameLabel.Top + WizardForm.PageNameLabel.Height + ScaleY(3);
  WizardForm.PageDescriptionLabel.Width := WizardForm.PageNameLabel.Width;
  WizardForm.PageDescriptionLabel.Font.Name := 'Consolas';
  WizardForm.PageDescriptionLabel.Font.Size := 8;
  WizardForm.PageDescriptionLabel.Font.Color := {#ColorTextSilver};

  // 2. Monospace y fondo oscuro para visores de texto
  WizardForm.InfoBeforeMemo.Font.Name := 'Consolas';
  WizardForm.InfoBeforeMemo.Font.Size := 9;
  WizardForm.InfoBeforeMemo.Color := {#ColorHeaderBg};
  WizardForm.InfoBeforeMemo.Font.Color := {#ColorLimeGreen};

  WizardForm.LicenseMemo.Font.Name := 'Consolas';
  WizardForm.LicenseMemo.Font.Size := 9;
  WizardForm.LicenseMemo.Color := {#ColorHeaderBg};
  WizardForm.LicenseMemo.Font.Color := {#ColorTextSilver};

  // 3. Bordes en Rosa Neón para botones
  BackBorderPanel := CreateNeonBorder(WizardForm.BackButton);
  NextBorderPanel := CreateNeonBorder(WizardForm.NextButton);
  CancelBorderPanel := CreateNeonBorder(WizardForm.CancelButton);

  // 4. Bordes en Rosa Neón para cajas y elementos
  InfoBeforeBorder := CreateNeonBorder(WizardForm.InfoBeforeMemo);
  LicenseBorder := CreateNeonBorder(WizardForm.LicenseMemo);
  DirEditBorder := CreateNeonBorder(WizardForm.DirEdit);
  BrowseBorderPanel := CreateNeonBorder(WizardForm.DirBrowseButton);
  ProgressBorder := CreateNeonBorder(WizardForm.ProgressGauge);

  // Línea divisoria inferior sobre la barra de acciones
  BottomLine := TPanel.Create(WizardForm);
  BottomLine.Parent := WizardForm;
  BottomLine.Left := 0;
  BottomLine.Top := WizardForm.BackButton.Top - ScaleY(12);
  BottomLine.Width := WizardForm.ClientWidth;
  BottomLine.Height := ScaleY(1);
  BottomLine.Color := {#ColorNeonPink};
  BottomLine.BevelOuter := bvNone;

  // 5. Destino fijo en Archivos de programa. No hay opción de %LOCALAPPDATA%.
  AllUsersRadio := TRadioButton.Create(WizardForm);
  AllUsersRadio.Parent := WizardForm.SelectDirPage;
  AllUsersRadio.Left := WizardForm.DirEdit.Left;
  AllUsersRadio.Top := WizardForm.DiskSpaceLabel.Top + WizardForm.DiskSpaceLabel.Height + ScaleY(8);
  AllUsersRadio.Width := WizardForm.SelectDirPage.Width - WizardForm.DirEdit.Left;
  AllUsersRadio.Height := ScaleY(20);
  AllUsersRadio.Caption := CustomMessage('AllUsersInstallCaption');
  AllUsersRadio.Checked := True;
  AllUsersRadio.OnClick := @OnScopeChange;
  WizardForm.DirEdit.Text := ExpandConstant('{#MyDefaultDirName}');

  PortableCheckBox := TCheckBox.Create(WizardForm);
  PortableCheckBox.Parent := WizardForm.SelectDirPage;
  PortableCheckBox.Left := WizardForm.DirEdit.Left;
  PortableCheckBox.Top := AllUsersRadio.Top + AllUsersRadio.Height + ScaleY(8);
  PortableCheckBox.Width := WizardForm.SelectDirPage.Width - WizardForm.DirEdit.Left;
  PortableCheckBox.Height := ScaleY(22);
  PortableCheckBox.Caption := CustomMessage('PortableCheckboxCaption');
  PortableCheckBox.Checked := False;
  PortableCheckBox.OnClick := @OnScopeChange;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  case CurPageID of
    wpInfoBefore:
    begin
      WizardForm.PageNameLabel.Caption := CustomMessage('Step1Title');
      WizardForm.PageDescriptionLabel.Caption := CustomMessage('Step1SubTitle');
    end;
    wpLicense:
    begin
      WizardForm.PageNameLabel.Caption := CustomMessage('Step2Title');
      WizardForm.PageDescriptionLabel.Caption := CustomMessage('Step2SubTitle');
    end;
    wpSelectDir:
    begin
      WizardForm.PageNameLabel.Caption := CustomMessage('Step3Title');
      WizardForm.PageDescriptionLabel.Caption := CustomMessage('Step3SubTitle');
    end;
    wpReady:
    begin
      WizardForm.PageNameLabel.Caption := CustomMessage('Step4Title');
      WizardForm.PageDescriptionLabel.Caption := CustomMessage('Step4SubTitle');
    end;
    wpInstalling:
    begin
      WizardForm.PageNameLabel.Caption := CustomMessage('Step5Title');
      WizardForm.PageDescriptionLabel.Caption := CustomMessage('Step5SubTitle');

      // Barra de progreso en Verde Lima sobre fondo oscuro
      SetWindowTheme(WizardForm.ProgressGauge.Handle, '', '');
      SendMessage(WizardForm.ProgressGauge.Handle, $0409, 0, {#ColorLimeGreen});
      SendMessage(WizardForm.ProgressGauge.Handle, $2001, 0, {#ColorProgressBg});
    end;
  end;

  if BackBorderPanel <> nil then
    BackBorderPanel.Visible := WizardForm.BackButton.Visible;
  if NextBorderPanel <> nil then
    NextBorderPanel.Visible := WizardForm.NextButton.Visible;
  if CancelBorderPanel <> nil then
    CancelBorderPanel.Visible := WizardForm.CancelButton.Visible;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and IsPortable() then
  begin
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + ExpandConstant('{#MyAppId}') + '_is1');
    RegDeleteKeyIncludingSubkeys(HKEY_LOCAL_MACHINE, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + ExpandConstant('{#MyAppId}') + '_is1');
    DeleteFile(ExpandConstant('{app}\unins000.exe'));
    DeleteFile(ExpandConstant('{app}\unins000.dat'));
  end;
end;
