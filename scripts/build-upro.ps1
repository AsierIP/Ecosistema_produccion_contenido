param(
    [ValidateSet('Thin', 'Bundled')][string]$Mode = 'Thin',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildDir = Join-Path $repo '.runtime\build\upro'
$distDir = Join-Path $repo '.runtime\dist\Upro'
New-Item -ItemType Directory -Force -Path $buildDir, $distDir | Out-Null
$pythonExe = (& $Python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw 'No se encuentra Python. Indica su ruta con -Python.'
}
& $pythonExe (Join-Path $repo 'scripts\upro_launcher.py') --root $repo --check
if ($LASTEXITCODE -ne 0) { throw 'La comprobacion de Upro ha fallado; no se empaqueta.' }

if ($Mode -eq 'Bundled') {
    & $pythonExe -c 'import PyInstaller' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller no esta instalado en este interprete. Usa -Mode Thin sin descargas o un entorno de empaquetado con PyInstaller.'
    }
    $staticDir = Join-Path $repo 'ecosystem\static'
    if (-not (Test-Path -LiteralPath $staticDir -PathType Container)) { throw 'Faltan los archivos del panel en ecosystem\static.' }
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --name Upro `
        --paths $repo --hidden-import ecosystem.upro --collect-submodules ecosystem `
        --add-data "$staticDir;ecosystem/static" --distpath (Join-Path $repo '.runtime\dist') `
        --workpath (Join-Path $buildDir 'pyinstaller') --specpath $buildDir `
        (Join-Path $repo 'scripts\upro_launcher.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller no pudo generar Upro.exe.' }
} else {
    # Windows includes this compiler; the launcher uses the existing Python installation.
    $compiler = @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $compiler) { throw 'Falta el compilador .NET Framework. Usa Upro.cmd o -Mode Bundled en un entorno con PyInstaller.' }
    $source = @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class UproLauncher {
    private const string BuiltPython = @"__PYTHON__";
    private const string BuiltRoot = @"__ROOT__";
    // Quote one Windows argument, including trailing slashes and literal quotes.
    private static string Quote(string value) {
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { result.Append('\\', slashes * 2 + 1); result.Append(c); slashes = 0; continue; }
            result.Append('\\', slashes); slashes = 0; result.Append(c);
        }
        result.Append('\\', slashes * 2); result.Append('"');
        return result.ToString();
    }
    private static string Root(string[] args) {
        for (int i = 0; i < args.Length; i++) {
            if (args[i] == "--root" && i + 1 < args.Length) return Path.GetFullPath(args[i + 1]);
            if (args[i].StartsWith("--root=")) return Path.GetFullPath(args[i].Substring(7));
        }
        DirectoryInfo candidate = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
        while (candidate != null) {
            if (File.Exists(Path.Combine(candidate.FullName, "scripts", "upro_launcher.py")) &&
                Directory.Exists(Path.Combine(candidate.FullName, "channels"))) return candidate.FullName;
            candidate = candidate.Parent;
        }
        if (File.Exists(Path.Combine(BuiltRoot, "scripts", "upro_launcher.py")) &&
            Directory.Exists(Path.Combine(BuiltRoot, "channels"))) return BuiltRoot;
        throw new Exception("No encuentro el proyecto Upro. Manten Upro.exe dentro del repositorio o indica --root.");
    }
    [STAThread]
    private static int Main(string[] args) {
        bool quiet = Array.IndexOf(args, "--check") >= 0 || Array.IndexOf(args, "--no-browser") >= 0;
        try {
            string root = Root(args);
            string launcher = Path.Combine(root, "scripts", "upro_launcher.py");
            if (!File.Exists(launcher)) throw new Exception("Falta scripts/upro_launcher.py en el proyecto seleccionado.");
            string python = Environment.GetEnvironmentVariable("UPRO_PYTHON");
            if (String.IsNullOrEmpty(python)) python = BuiltPython;
            if (!File.Exists(python)) throw new Exception("No encuentro Python. Reconstruye Upro.exe o define UPRO_PYTHON con la ruta de python.exe.");
            StringBuilder command = new StringBuilder(Quote(launcher) + " --root " + Quote(root));
            foreach (string arg in args) command.Append(" " + Quote(arg));
            ProcessStartInfo start = new ProcessStartInfo(python, command.ToString());
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WindowStyle = ProcessWindowStyle.Hidden;
            using (Process child = Process.Start(start)) {
                if (child == null) throw new Exception("No se ha podido iniciar el motor Upro.");
                child.WaitForExit();
                return child.ExitCode;
            }
        } catch (Exception error) {
            if (!quiet) MessageBox.Show(error.Message, "Upro - error al iniciar", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
'@
    $source = $source.Replace('__PYTHON__', $pythonExe.Replace('"', '""'))
    $source = $source.Replace('__ROOT__', $repo.Replace('"', '""'))
    $sourceFile = Join-Path $buildDir 'UproLauncher.cs'
    [IO.File]::WriteAllText($sourceFile, $source, (New-Object Text.UTF8Encoding($false)))
    $exe = Join-Path $distDir 'Upro.exe'
    & $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll "/out:$exe" $sourceFile
    if ($LASTEXITCODE -ne 0) { throw 'No se ha podido compilar el ejecutable Upro.' }
}

$exe = Join-Path $distDir 'Upro.exe'
$check = Start-Process -FilePath $exe -ArgumentList '--check' -WindowStyle Hidden -Wait -PassThru
if ($check.ExitCode -ne 0) { throw "Upro.exe ha fallado su comprobacion ($($check.ExitCode))." }
[ordered]@{
    app = 'Upro'
    mode = $Mode
    executable = $exe
    sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    installation_check = 'PASS'
    full_production_verified = $false
} | ConvertTo-Json
