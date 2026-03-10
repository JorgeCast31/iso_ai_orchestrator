# iso-ai-orchestrator

Pipeline para generación y auditoría de documentación técnica estilo ISO para equipos de laboratorio usando modelos de lenguaje (LLMs).

## Propósito
Automatiza la creación de procedimientos técnicos (POE, instructivos, planes de mantenimiento, checklists de auditoría) mediante un flujo de generación y revisión con modelos Claude (Anthropic) y GPT (OpenAI).

## Arquitectura del pipeline
1. **Claude (Anthropic):** Genera borrador de POE a partir de plantilla y plan maestro.
2. **GPT (OpenAI):** Audita el documento como auditor ISO y detecta huecos documentales.
3. **Claude:** Reescribe el documento considerando la auditoría.
4. **Resultado:** Documento final guardado en outputs/.

## Instalación

1. Crear entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Configurar variables de entorno:
   - Copiar `.env.example` a `.env` y agregar tus claves API.

## Ejecución del pipeline

```bash
python src/orchestrator.py
```

## Estructura del repositorio
```
iso-ai-orchestrator/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ .env.example
├─ inputs/
├─ outputs/
├─ prompts/
├─ src/
└─ tests/
```

## Listo para git y GitHub
Inicializa el repositorio con:
```bash
git init
git add .
git commit -m "Initial commit"
```
