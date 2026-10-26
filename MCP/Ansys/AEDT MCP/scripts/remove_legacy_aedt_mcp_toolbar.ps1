#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$AedtRoot,
    [string[]]$Toolkits = @("HFSS", "Project"),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$KnownLabels = @("Codex MCP", "Start AEDT MCP Bridge", "Stop AEDT MCP Bridge")
$KnownScripts = @("AEDT MCP.py", "Start AEDT MCP Bridge.py", "Stop AEDT MCP Bridge.py")

foreach ($toolkit in $Toolkits) {
    $toolkitDir = Join-Path (Join-Path $AedtRoot "syslib\Toolkits") $toolkit
    $tabConfigPath = Join-Path $toolkitDir "TabConfig.xml"
    if (-not (Test-Path -LiteralPath $tabConfigPath)) {
        Write-Warning "Skipping missing Toolkit configuration: $tabConfigPath"
        continue
    }

    [xml]$xml = Get-Content -LiteralPath $tabConfigPath -Encoding UTF8
    $nodes = @()
    foreach ($label in $KnownLabels) {
        $nodes += @($xml.SelectNodes("//*[@label='$label']"))
    }

    if ($DryRun) {
        Write-Host "[AEDT MCP] ${toolkit}: would remove $($nodes.Count) known XML node(s)."
    }
    else {
        foreach ($node in $nodes) {
            if ($null -ne $node.ParentNode) {
                [void]$node.ParentNode.RemoveChild($node)
            }
        }
        $settings = New-Object System.Xml.XmlWriterSettings
        $settings.Indent = $true
        $settings.Encoding = New-Object System.Text.UTF8Encoding($false)
        $writer = [System.Xml.XmlWriter]::Create($tabConfigPath, $settings)
        try {
            $xml.Save($writer)
        }
        finally {
            $writer.Close()
        }
    }

    foreach ($scriptName in $KnownScripts) {
        $scriptPath = Join-Path $toolkitDir $scriptName
        if (Test-Path -LiteralPath $scriptPath) {
            if ($DryRun) {
                Write-Host "[AEDT MCP] ${toolkit}: would remove $scriptPath"
            }
            else {
                Remove-Item -LiteralPath $scriptPath -Force
            }
        }
    }
}

Write-Host "[AEDT MCP] Legacy toolbar cleanup complete. Backups were preserved."
