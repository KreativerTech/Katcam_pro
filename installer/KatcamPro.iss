; KatcamPro.iss — Instalador Inno Setup (sin preprocesador)
; Estructura sugerida:
; Katcam_pro\
; ├─ assets\
; │   ├─ katcam_multi.ico
; │   ├─ logo_katcam.png
; │   ├─ logo_kreativer.png
; │   └─ header-katcam.jpg
; ├─ dist\
; │   └─ KatcamPro.exe
; └─ installer\
;     ├─ KatcamPro.iss          ; este archivo
;     ├─ wizard_image.bmp       ; 164x314
;     └─ wizard_small_image.bmp ; 55x55

[Setup]
; --- Datos de la app ---
AppId={{F3F7E7B9-4EC1-4D4B-B2D4-1C9D2E12A3D7}
AppName=Katcam Pro
AppVersion=2.3.0
AppPublisher=KreativerTech
AppPublisherURL=https://kreativer.tech

; --- Rutas/estilo ---
DefaultDirName={autopf}\KreativerTech\Katcam Pro
DefaultGroupName=Katcam Pro
DisableProgramGroupPage=yes
OutputBaseFilename=KatcamPro-Setup-2.3.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

; Icono y bitmaps del wizard
SetupIconFile=..\assets\katcam_multi.ico
WizardImageFile=wizard_image.bmp
WizardSmallImageFile=wizard_small_image.bmp

; Para actualizar instalaciones con archivos en uso
CloseApplications=yes
ChangesAssociations=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
Name: "autostart"; Description: "Iniciar Katcam Pro con Windows"; GroupDescription: "Opciones adicionales:"; Flags: unchecked
Name: "runapp"; Description: "Ejecutar Katcam Pro al finalizar"; GroupDescription: "Acciones al finalizar:"; Flags: checkedonce

[Dirs]
; Carpeta de datos compartidos (JSON de configuración)
Name: "{commonappdata}\KreativerTech\KatcamPro"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
; Binario principal (salida de PyInstaller)
Source: "..\dist\KatcamPro.exe"; DestDir: "{app}"; Flags: ignoreversion
; Assets usados por la app en runtime
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Katcam Pro"; Filename: "{app}\KatcamPro.exe"; IconFilename: "{app}\assets\katcam_multi.ico"; WorkingDir: "{app}"
Name: "{commondesktop}\Katcam Pro"; Filename: "{app}\KatcamPro.exe"; IconFilename: "{app}\assets\katcam_multi.ico"; Tasks: desktopicon; WorkingDir: "{app}"

[Registry]
; Autostart opcional (usuario actual)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "Katcam Pro"; ValueData: """{app}\KatcamPro.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; Ejecutar al finalizar si el usuario marca la opción
Filename: "{app}\KatcamPro.exe"; Description: "Ejecutar Katcam Pro"; Flags: nowait postinstall skipifsilent; Tasks: runapp

;-------------------------
; PÁGINA PERSONALIZADA: Datos del proyecto
;-------------------------
[Code]
var
  PgDatos: TInputQueryWizardPage;

function JsonEscape(const S: string): string;
var
  i: Integer;
  ch: Char;
begin
  Result := '';
  for i := 1 to Length(S) do
  begin
    ch := S[i];
    case ch of
      '"':  Result := Result + '\"';
      '\':  Result := Result + '\\';
    else
      Result := Result + ch;
    end;
  end;
end;


procedure InitializeWizard;
begin
  PgDatos := CreateInputQueryPage(
    wpSelectTasks,
    'Información del proyecto',
    'Ingresa los datos de tu instalación',
    'Estos datos se guardarán en la configuración de la aplicación y podrás modificarlos más tarde desde la app.'
  );
  PgDatos.Add('Nombre del equipo:', False);
  PgDatos.Add('Cliente:', False);
  PgDatos.Add('Obra:', False);
  PgDatos.Add('Ubicación:', False);
  PgDatos.Add('Contacto:', False);
  PgDatos.Add('GPS Latitud:', False);
  PgDatos.Add('GPS Longitud:', False);

  // Valores por defecto (vacíos)
  PgDatos.Values[0] := '';
  PgDatos.Values[1] := '';
  PgDatos.Values[2] := '';
  PgDatos.Values[3] := '';
  PgDatos.Values[4] := '';
  PgDatos.Values[5] := '';
  PgDatos.Values[6] := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  // Validación: exigir al menos "Nombre del equipo"
  if CurPageID = PgDatos.ID then
  begin
    if Trim(PgDatos.Values[0]) = '' then
    begin
      MsgBox('Por favor ingresa el "Nombre del equipo".', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigPath, Json: string;
  camera_id, cliente, obra, ubicacion, contacto, lat, lon: string;
begin
  if CurStep = ssPostInstall then
  begin
    // Construir JSON y guardarlo en ProgramData
    camera_id := JsonEscape(PgDatos.Values[0]);
    cliente   := JsonEscape(PgDatos.Values[1]);
    obra      := JsonEscape(PgDatos.Values[2]);
    ubicacion := JsonEscape(PgDatos.Values[3]);
    contacto  := JsonEscape(PgDatos.Values[4]);
    lat       := JsonEscape(PgDatos.Values[5]);
    lon       := JsonEscape(PgDatos.Values[6]);

    ConfigDir  := ExpandConstant('{commonappdata}\KreativerTech\KatcamPro');
    ConfigPath := ConfigDir + '\katcam_config.json';

    Json :=
      '{' + #13#10 +
      '  "version": "2.2.0",' + #13#10 +
      '  "autor": "KreativerTech",' + #13#10 +
      '  "soporte": "support@kreativer.tech",' + #13#10 +
      '  "camera_id": "' + camera_id + '",' + #13#10 +
      '  "cliente": "' + cliente + '",' + #13#10 +
      '  "obra": "' + obra + '",' + #13#10 +
      '  "ubicacion": "' + ubicacion + '",' + #13#10 +
      '  "contacto": "' + contacto + '",' + #13#10 +
      '  "gps_lat": "' + lat + '",' + #13#10 +
      '  "gps_lon": "' + lon + '"' + #13#10 +
      '}';

    if not DirExists(ConfigDir) then
      ForceDirectories(ConfigDir);

    if not SaveStringToFile(ConfigPath, Json, False) then
      MsgBox('No se pudo escribir la configuración en: ' + ConfigPath, mbError, MB_OK);
  end;
end;
