# agente_traductor_video

Pipeline local para transcribir, traducir y doblar videos. Corre completamente en tu máquina sin depender de servicios de pago.

```
Video original  →  Transcripción (Faster-Whisper)
                →  Traducción (Ollama)
                →  Síntesis de voz (Edge-TTS o Kokoro)
                →  Video doblado (FFmpeg)
```

---

## Requisitos previos

| Herramienta | Para qué se usa | Instalación |
|---|---|---|
| Python 3.11+ | Runtime | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | Gestor de paquetes | `pip install uv` |
| [FFmpeg](https://ffmpeg.org/download.html) | Mezcla audio+video | Debe estar en PATH (`ffmpeg -version`) |
| [Ollama](https://ollama.com) | LLM local para traducción | Instalar + `ollama pull qwen2.5-coder` |
| GPU NVIDIA (opcional) | Acelera la transcripción | CUDA 12 recomendado |

---

## Instalación

```powershell
git clone https://github.com/josealcidesvalenzuela-boop/agente_traductor_video
cd agente_traductor_video
uv sync
```

Copia el archivo de configuración y ajústalo si es necesario:

```powershell
copy .env.example .env
```

---

## Uso rápido

```powershell
# Traducir un video de inglés a español
.\traducir.ps1 run video.mkv --source en --target es

# Con detección automática del idioma origen
.\traducir.ps1 run video.mp4 --target es
```

Todos los archivos generados se guardan en `salida/video_YYYYMMDD_HHMMSS/`.

---

## Estructura de salida

Cada ejecución crea una subcarpeta con timestamp en `salida/`:

```
salida/
└── mi_video_20260522_143500/
    ├── transcription.srt    ← subtítulos del audio original
    ├── translated.srt       ← subtítulos traducidos
    ├── tts/                 ← segmentos de audio sintetizados
    │   ├── seg_0001.mp3
    │   ├── seg_0002.mp3
    │   └── …
    └── dubbed.mp4           ← video final con la nueva voz
```

---

## Referencia de comandos

### `run` — pipeline completo

```powershell
.\traducir.ps1 run <video> [opciones]
```

| Opción | Default | Descripción |
|---|---|---|
| `--source`, `-s` | `auto` | Idioma del audio original. `auto` detecta automáticamente |
| `--target`, `-t` | `en` | Idioma de destino: `en`, `es`, `fr`, `de`, `it`, `pt`, `zh`, `ja`, `ko`, `ru`, `ar` |
| `--engine` | `edge` | Motor TTS: `edge` (nube, requiere internet) o `kokoro` (local, ~300 MB) |
| `--voice` | automático | Nombre de voz explícito. Ver `voices` para listar opciones |
| `--tone` | `neutral` | Tono de traducción: `neutral`, `formal`, `informal` |
| `--domain` | `general` | Dominio del contenido: `general`, `technical`, `casual` |
| `--only` | — | Ejecutar solo una etapa: `transcribe`, `translate`, `tts`, `merge` |
| `--srt` | — | SRT existente (omite la transcripción) |
| `--output`, `-o` | `salida/…/dubbed.mp4` | Ruta personalizada para el video de salida |
| `--force`, `-f` | — | Ignorar archivos previos y reejecutar desde cero |

#### Ejemplos

```powershell
# Inglés → Español con Edge-TTS (defecto)
.\traducir.ps1 run conferencia.mkv --source en --target es

# Con voz específica
.\traducir.ps1 run conferencia.mkv --source en --target es --voice es-MX-JorgeNeural

# Usar Kokoro (TTS local, sin internet)
.\traducir.ps1 run conferencia.mkv --source en --target es --engine kokoro

# Tono formal para contenido corporativo
.\traducir.ps1 run presentacion.mp4 --source en --target es --tone formal --domain technical

# Japonés → Inglés
.\traducir.ps1 run anime.mkv --source ja --target en

# Si ya tienes el SRT, salta la transcripción
.\traducir.ps1 run video.mkv --srt mis_subtitulos.srt --target fr

# Reejecutar aunque ya existan archivos previos
.\traducir.ps1 run video.mkv --source en --target es --force

# Solo transcribir (sin traducir ni doblar)
.\traducir.ps1 run video.mkv --only transcribe

# Solo sintetizar voz a partir de un SRT traducido
.\traducir.ps1 run video.mkv --only tts --srt salida/video_20260522_143500/translated.srt
```

#### Retomar una ejecución interrumpida

Si el pipeline se corta a mitad, simplemente vuelve a ejecutar el mismo comando **sin `--force`**. El sistema detecta la última ejecución y reutiliza los archivos ya generados:

```powershell
# La primera vez falló en la etapa TTS
.\traducir.ps1 run conferencia.mkv --source en --target es
# → Reutiliza transcription.srt y translated.srt, retoma desde TTS
```

---

### `voices` — listar voces disponibles

```powershell
.\traducir.ps1 voices [idioma] [--engine edge|kokoro]
```

```powershell
# Todas las voces de Edge-TTS
.\traducir.ps1 voices

# Voces en español (Edge-TTS)
.\traducir.ps1 voices es

# Voces en inglés americano (Edge-TTS)
.\traducir.ps1 voices en-US

# Todas las voces de Kokoro
.\traducir.ps1 voices --engine kokoro

# Voces en español de Kokoro (prefijo "ef" = español femenino)
.\traducir.ps1 voices ef --engine kokoro
```

---

## Motores TTS

### Edge-TTS (defecto)

- Requiere conexión a internet en cada ejecución
- +400 voces en más de 40 idiomas
- Calidad alta, sin descarga previa

```powershell
.\traducir.ps1 run video.mkv --target es --engine edge --voice es-ES-ElviraNeural
```

### Kokoro (local)

- Funciona sin internet después de la primera descarga (~300 MB, descarga automática)
- 54 voces en 9 idiomas
- Ideal para uso frecuente o entornos sin internet

```powershell
.\traducir.ps1 run video.mkv --target es --engine kokoro --voice ef_dora
```

| Prefijo | Idioma |
|---|---|
| `af_`, `am_` | Inglés americano (♀/♂) |
| `bf_`, `bm_` | Inglés británico (♀/♂) |
| `ef_`, `em_` | Español (♀/♂) |
| `ff_` | Francés (♀) |
| `if_`, `im_` | Italiano (♀/♂) |
| `jf_`, `jm_` | Japonés (♀/♂) |
| `pf_`, `pm_` | Portugués (♀/♂) |
| `zf_`, `zm_` | Chino mandarín (♀/♂) |
| `hf_`, `hm_` | Hindi (♀/♂) |

---

## Configuración

Variables de entorno (archivo `.env`):

| Variable | Default | Descripción |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | Modelo de transcripción: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | *(auto)* | Forzar dispositivo: dejar vacío para auto-detectar, `cpu` para deshabilitar CUDA |
| `OLLAMA_HOST` | `http://localhost:11434` | Endpoint del servidor Ollama |
| `OLLAMA_MODEL` | `qwen2.5-coder` | Modelo LLM para traducción |
| `TTS_ENGINE` | `edge` | Motor TTS por defecto: `edge` o `kokoro` |

### Modelos Whisper

| Modelo | VRAM aprox. | Velocidad | Calidad |
|---|---|---|---|
| `tiny` | ~1 GB | Muy rápido | Básica |
| `base` | ~1 GB | Rápido | Aceptable |
| `small` | ~2 GB | Rápido | Buena |
| `medium` | ~5 GB | Moderado | Muy buena |
| `large-v3` | ~10 GB | Lento | Excelente |

Para pruebas rápidas: `WHISPER_MODEL=small` en `.env`.

### Modelos Ollama recomendados

```powershell
# Recomendado (buen balance calidad/velocidad)
ollama pull qwen2.5-coder

# Alternativa general
ollama pull llama3.2

# Para hardware limitado
ollama pull llama3.2:1b
```

---

## Solución de problemas

**`RuntimeError: Library cublas64_12.dll is not found`**  
Usar `.\traducir.ps1` en lugar de `uv run python main.py` directamente. El script agrega las DLLs de NVIDIA al PATH.

**`Connection refused` al traducir**  
Ollama no está corriendo. Ejecutar `ollama serve` en otra terminal (o como servicio de Windows).

**Transcripción muy lenta**  
CUDA no está disponible. Verificar con `nvidia-smi`. Si el problema persiste, usar un modelo más pequeño: `WHISPER_MODEL=small` en `.env`.

**El audio suena acelerado**  
Normal para subtítulos muy largos en un intervalo corto. La velocidad se ajusta automáticamente hasta un máximo de 1.5×.
