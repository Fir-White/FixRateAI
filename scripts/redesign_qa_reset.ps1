$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'redesign_qa_stop.ps1')
& (Join-Path $PSScriptRoot 'redesign_qa_start.ps1')
