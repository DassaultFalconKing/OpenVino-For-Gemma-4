# Запуск Gemma4 Server на Windows

Нужны Windows x64, Intel GPU с установленным драйвером, **полный пакет нашего OVMS** и модель в формате OpenVINO. ZIP исходников этого репозитория не содержит сервер и веса.

Распакуйте проект в удобное место. Рекомендуемое имя папки — `Gemma4-Server-windows-x64`:

```text
Gemma4-Server-windows-x64/
  Start-Server.ps1       запуск сервера
  START-HERE.md         эта инструкция
  opencode.json         provider для OpenCode
  server/               полный OVMS-пакет: ovms.exe, DLL, python/ и остальные файлы
  models/gemma4/        все файлы модели: config.json, XML, BIN, токенизатор и шаблон
  ovms/                 настройки и вспомогательные скрипты проекта
  generated-config/     создаётся автоматически; вручную редактировать не нужно
```

1. Положите **всё содержимое** OVMS-пакета в `server`, а модель — в `models\gemma4`. Файлы `server\ovms.exe` и `models\gemma4\config.json` должны находиться именно по этим путям, без лишнего уровня вложенности.
2. Откройте PowerShell в папке проекта и выполните:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Server.ps1
   ```

3. Дождитесь `AVAILABLE`. В NovaClaw или другом клиенте укажите:
   - **Base URL:** `http://127.0.0.1:9090/v3`
   - **Model:** `gemma4`
   - **API key:** не требуется; если поле обязательное — `local`.

OpenCode подхватит provider `gemma4-local` из `opencode.json`, если запускать его из этой папки. В выборе модели используйте `gemma4-local/gemma4-26-heretic`. Для другого проекта скопируйте этот файл в его корень или добавьте блок `provider` в существующий `opencode.json`.

Оставьте окно открытым. Для остановки нажмите **Ctrl+C**. Список моделей можно проверить в браузере: `http://127.0.0.1:9090/v3/models`.

Если сервер и модель уже лежат в других папках, переносить их не нужно:

```powershell
.\Start-Server.ps1 -OvmsExe 'D:\OVMS\ovms.exe' -ModelPath 'D:\Models\Gemma4'
```

Другой порт: добавьте `-Port 8000` и измените URL клиента. Если порт занят, остановите предыдущий сервер или выберите другой порт.

По умолчанию включён проверенный профиль `vlm-stable` с отключённой очередью графов (`OVMS_GRAPH_QUEUE_MAX_SIZE: 0`): это устраняет воспроизведённое зависание параллельных запросов. Модель выполняет запросы последовательно. Названия папок сборки и SHA не нужно вводить в настройках клиента.
