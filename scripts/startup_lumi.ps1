# ============================================================================
# LUMI Startup Script — Windows Boot Auto-Start
# ============================================================================
# Ye script system start hone pe:
#   1. Ollama service start karta hai (web server ke liye)
#   2. LUMI web server start karta hai (http://127.0.0.1:8765)
#   3. Agar QLoRA training incomplete hai, toh Ollama band karke training resume karta hai
#   4. Training complete hone pe Ollama dobara start karta hai
# ============================================================================

$ErrorActionPreference = 'Continue'
$LUMI_DIR = "."
cd $LUMI_DIR

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
}

Log "========================================"
Log "LUMI Startup Script — Auto-Resuming..."
Log "========================================"

# -----------------------------------------------------------
# 1. Start Ollama service (needed for web server + chat)
# -----------------------------------------------------------
Log "[1/4] Starting Ollama service..."
$ollamaSvc = Get-Service -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaSvc -and $ollamaSvc.Status -ne 'Running') {
    Start-Service -Name "ollama" -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 5
$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProc) {
    Log "   Ollama is running (PID: $($ollamaProc.Id))"
} else {
    Log "   WARNING: Ollama process not detected. Web chat may fail."
}

# -----------------------------------------------------------
# 2. Start LUMI Web Server if not already running
# -----------------------------------------------------------
Log "[2/4] Checking LUMI Web Server..."
$webProc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*main.py*" -and $_.CommandLine -like "*--web*"
}
if ($webProc) {
    Log "   Web server already running (PID: $($webProc.Id))"
} else {
    Log "   Starting LUMI Web Server..."
    Start-Process python -ArgumentList "main.py --web" -WorkingDirectory $LUMI_DIR -WindowStyle Hidden
    Start-Sleep -Seconds 6
    $webProc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*main.py*" -and $_.CommandLine -like "*--web*"
    }
    if ($webProc) {
        Log "   Web server started (PID: $($webProc.Id)) — http://127.0.0.1:8765"
    } else {
        Log "   WARNING: Web server may not have started. Check web_server.log"
    }
}

# -----------------------------------------------------------
# 3. Check training state — resume if incomplete
# -----------------------------------------------------------
Log "[3/4] Checking QLoRA training state..."
$summaryPath = Join-Path $LUMI_DIR "models\lumi-qwen3-4b-hinglish\training_summary.json"
$manifestPath = Join-Path $LUMI_DIR "data\massive\manifest.json"

if (-not (Test-Path $manifestPath)) {
    Log "   Training data not found. Skipping training resume."
}
elseif (Test-Path $summaryPath) {
    $summary = Get-Content $summaryPath | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($summary) {
        $completed = $summary.completed_sets
        $total = $summary.total_sets
        Log "   Training summary: $completed / $total sets completed"

        if ($completed -ge $total) {
            Log "   Training is COMPLETE. No resume needed."
        } else {
            Log "   Training INCOMPLETE. Resuming from set $completed..."

            # Stop Ollama to free full 8GB VRAM for training
            Log "[4/4] Stopping Ollama for training VRAM..."
            Stop-Service -Name "ollama" -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 5
            $ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
            if ($ollamaProc) {
                Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
            }
            Log "   Ollama stopped. GPU VRAM now free."

            # Resume training
            Log "   Starting QLoRA set-wise training..."
            python $LUMI_DIR/scripts/set_wise_trainer.py `
                --config $LUMI_DIR/config/finetune.yaml `
                --data-dir $LUMI_DIR/data/massive `
                --base-model Qwen/Qwen2.5-3B-Instruct
            $trainingExitCode = $LASTEXITCODE

            # Restart Ollama after training
            Log "   Restarting Ollama service after training..."
            Start-Service -Name "ollama" -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 5
            $ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
            if ($ollamaProc) {
                Log "   Ollama restarted successfully."
            } else {
                Log "   WARNING: Ollama did not restart. Run 'ollama serve' manually."
            }

            if ($trainingExitCode -eq 0) {
                Log "   Training session completed successfully!"
            } else {
                Log "   Training exited with code $trainingExitCode (may resume on next boot)."
            }
        }
    } else {
        Log "   Training summary file exists but could not be parsed."
    }
} else {
    Log "   No training summary found. Fresh training not configured to start automatically."
    Log "   To start training manually: python scripts/set_wise_trainer.py --config config/finetune.yaml --data-dir data/massive --base-model Qwen/Qwen2.5-3B-Instruct"
}

Log "========================================"
Log "LUMI Startup Complete."
Log "========================================"
