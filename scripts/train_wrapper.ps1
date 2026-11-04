# LUMI Training Wrapper — Stop Ollama, Train, Restart Ollama
# Run: powershell -ExecutionPolicy Bypass -File scripts\train_wrapper.ps1

# Step 1: Stop Ollama service to free GPU VRAM
Write-Host "Stopping Ollama service to free GPU VRAM..."
Stop-Service -Name "ollama" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

# Force kill if still running
$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProc) {
    Write-Host "Ollama process still running, force killing..."
    Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

Write-Host "Ollama stopped. GPU VRAM free for training."

# Step 2: Run set-wise training
Write-Host "Starting QLoRA set-wise training..."
python scripts\set_wise_trainer.py --config config\finetune.yaml --data-dir data\massive --base-model Qwen/Qwen2.5-3B-Instruct
$trainingExitCode = $LASTEXITCODE

# Step 3: Restart Ollama service
Write-Host "Restarting Ollama service..."
Start-Service -Name "ollama" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProc) {
    Write-Host "Ollama restarted successfully."
} else {
    Write-Host "Ollama may not have restarted. Run 'ollama serve' manually."
}

# Step 4: Report
if ($trainingExitCode -eq 0) {
    Write-Host "Training completed successfully!"
} else {
    Write-Host "Training exited with code $trainingExitCode"
}

Write-Host "Check training_log_v3.txt for progress and models\lumi-qwen3-4b-hinglish\ for saved adapters."
