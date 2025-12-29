; Katcam Pro Installer (.iss) - ROOT (coincide con tu árbol). AppData config, SIN GPS.

#define APP_VERSION "2.9.0"
#define APP_NAME    "Katcam Pro"
#define APP_PUBLISHER "Kreativer"

[Setup]
; --- Datos de la app ---
AppId={{F3F7E7B9-4EC1-4D4B-B2D4-1C9D2E12A3D7}}
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppPublisher={#APP_PUBLISHER}
AppPublisherURL=https://www.kreativer.cl

; --- Rutas/estilo ---
DefaultDirName={autopf}\KreativerTech\Katcam Pro
DefaultGroupName=Katcam Pro
DisableProgramGroupPage=yes
OutputBaseFilename=KatcamPro-Setup-{#APP_VERSION}
OutputDir=Output
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\assets\katcam_multi.ico
WizardImageFile=wizard_image.bmp
WizardSmallImageFile=wizard_small_image.bmp

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Registry]
; Autostart activado por defecto tras instalar. El usuario puede desactivarlo desde la app.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
ValueType: string; ValueName: "KatcamPro"; \
ValueData: "{app}\KatcamPro.exe"; Flags: uninsdeletevalue

[Files]
Source: "..\dist\KatcamPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Katcam Pro"; Filename: "{app}\KatcamPro.exe"
Name: "{commondesktop}\Katcam Pro"; Filename: "{app}\KatcamPro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KatcamPro.exe"; Description: "Ejecutar Katcam Pro"; Flags: nowait postinstall skipifsilent

; ===============================
;           CÓDIGO
; ===============================
[Code]

const
  NL = #13#10;
  APP_VERSION_STR = '{#APP_VERSION}';

var
  InfoPage: TInputQueryWizardPage;
  CameraId, Cliente, Obra, Ubicacion, Contacto: string;

function Hex4(N: Integer): string;
var
  s: string;
  d: Integer;
  hexDigits: string;
begin
  hexDigits := '0123456789ABCDEF';
  s := '';
  while N > 0 do
  begin
    d := N mod 16;
    s := Copy(hexDigits, d + 1, 1) + s;
    N := N div 16;
  end;
  while Length(s) < 4 do
    s := '0' + s;
  if s = '' then
    s := '0000';
  Result := s;
end;

function EscapeJson(const S: string): string;
var
  I: Integer;
  Ch: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    Ch := S[I];
    case Ch of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
    else
      case Ord(Ch) of
        8:  Result := Result + '\b';
        9:  Result := Result + '\t';
        10: Result := Result + '\n';
        12: Result := Result + '\f';
        13: Result := Result + '\r';
      else
        if Ord(Ch) < 32 then
          Result := Result + '\u' + Hex4(Ord(Ch))
        else
          Result := Result + Ch;
      end;
    end;
  end;
end;

function JsonString(const S: string): string;
begin
  Result := '"' + EscapeJson(S) + '"';
end;

procedure SaveConfigJson(const ACameraId, ACliente, AObra, AUbicacion, AContacto: string);
var
  Json, CfgDir, CfgPath: string;
begin
  Json :=
    '{' + NL +
    '  "version": "' + APP_VERSION_STR + '",' + NL +
    '  "autor": "Kreativer",' + NL +
    '  "soporte": "kreativer.empresa@gmail.com",' + NL +
    '  "camera_id": ' + JsonString(ACameraId) + ',' + NL +
    '  "cliente": '   + JsonString(ACliente)   + ',' + NL +
    '  "obra": '      + JsonString(AObra)      + ',' + NL +
    '  "ubicacion": ' + JsonString(AUbicacion) + ',' + NL +
    '  "contacto": '  + JsonString(AContacto)  + NL +
    '}';

  CfgDir := ExpandConstant('{userappdata}\KatcamPro');
  if not DirExists(CfgDir) then
    if not ForceDirectories(CfgDir) then
    begin
      MsgBox('No se pudo crear: ' + CfgDir, mbError, MB_OK);
      Exit;
    end;

  CfgPath := CfgDir + '\katcam_config.json';
  if not SaveStringToFile(CfgPath, Json, False) then
    MsgBox('No se pudo escribir la configuración en: ' + CfgPath, mbError, MB_OK);
end;

// ===== UI para capturar datos =====
procedure InitializeWizard;
begin
  InfoPage := CreateInputQueryPage(
    wpSelectDir,
    'Datos de Katcam',
    'Completa los datos de identificación',
    'Estos datos se guardarán en la configuración del usuario.'
  );
  InfoPage.Add('Nombre del equipo (obligatorio):', False);
  InfoPage.Add('Cliente:', False);
  InfoPage.Add('Obra:', False);
  InfoPage.Add('Ubicación:', False);
  InfoPage.Add('Contacto:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (InfoPage <> nil) and (CurPageID = InfoPage.ID) then
  begin
    if Trim(InfoPage.Values[0]) = '' then
    begin
      MsgBox('El "Nombre del equipo" es obligatorio.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    CameraId := InfoPage.Values[0];
    Cliente  := InfoPage.Values[1];
    Obra     := InfoPage.Values[2];
    Ubicacion:= InfoPage.Values[3];
    Contacto := InfoPage.Values[4];
  end;
end;

// ===== Guardar al terminar la instalación =====
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SaveConfigJson(CameraId, Cliente, Obra, Ubicacion, Contacto);
  end;
end;
