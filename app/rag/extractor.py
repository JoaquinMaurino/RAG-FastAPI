"""
Step 4: Extracción de texto de PDFs.

Responsabilidad única: dado un path de archivo, devolver el texto
en crudo (raw text) como un string.

¿Por qué está en app/rag/ y no en app/services/?
-------------------------------------------------
Los servicios (services/) contienen lógica de negocio que orquesta
recursos: base de datos, archivos, APIs externas.

El extractor es una función de TRANSFORMACIÓN pura:
    input:  ruta de un archivo en disco
    output: string de texto

No tiene efectos secundarios (no escribe en la DB, no llama APIs).
Ese tipo de lógica "pura" vive en rag/ junto al chunker, retriever,
etc. Son las "piezas" que los services orquestan.

Analogía:
    services/document_service.py  → Maestro de obra
    rag/extractor.py               → Herramienta específica

¿Por qué PyMuPDF?
-----------------
PyMuPDF (importado como `fitz`) usa el motor MuPDF escrito en C.
Es significativamente más rápido y preciso que pypdf/PyPDF2 para:
    - PDFs con múltiples columnas
    - Espaciado entre palabras
    - Caracteres especiales y acentos
    - PDFs con imágenes mezcladas con texto
"""

from pathlib import Path

import fitz  # PyMuPDF


class ExtractionError(Exception):
    """
    Excepción personalizada para errores de extracción.

    ¿Por qué una excepción propia en vez de usar ValueError o IOError?
    Porque nos da control granular en el service:

        try:
            text = extract_text_from_pdf(path)
        except ExtractionError as e:
            # Sabemos exactamente qué falló y podemos devolver
            # un HTTP 422 con un mensaje descriptivo al usuario.
        except Exception as e:
            # Error inesperado → HTTP 500

    Si usáramos ValueError, no podríamos distinguir si fue nuestro
    código o alguna otra librería la que lanzó el error.
    """
    pass


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extrae el texto completo de un archivo PDF.

    Itera página por página y concatena el texto de cada una.
    Usa un separador visual entre páginas para que el texto resultante
    sea coherente y no mezcle el final de una página con el inicio de la siguiente.

    Args:
        file_path: Ruta absoluta o relativa al archivo PDF en disco.

    Returns:
        String con todo el texto extraído del documento.

    Raises:
        ExtractionError: Si el archivo no existe, no es un PDF válido,
                         o si el PDF no contiene texto seleccionable
                         (por ejemplo, un PDF escaneado que requeriría OCR).
    """
    path = Path(file_path)

    # --- Validación 1: ¿El archivo existe? ---
    # Mejor fallar acá con un mensaje claro que dejar que fitz
    # lance su propio error interno (menos descriptivo).
    if not path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    # --- Validación 2: ¿Es un PDF? ---
    # Verificamos por extensión. En fases futuras podríamos verificar
    # también por magic bytes (los primeros bytes del archivo).
    if path.suffix.lower() != ".pdf":
        raise ExtractionError(
            f"Unsupported file type '{path.suffix}'. Only PDF files are supported."
        )

    try:
        # fitz.open() abre el documento PDF.
        # Usamos `with` para garantizar que el archivo se cierre
        # correctamente incluso si ocurre un error durante la extracción.
        with fitz.open(file_path) as doc:
            pages_text: list[str] = []

            for page_number, page in enumerate(doc, start=1):
                # get_text() extrae el texto de la página.
                # El parámetro "text" es el modo más simple: texto plano.
                # Otros modos disponibles: "html", "dict", "blocks", "words".
                # Para RAG, texto plano es suficiente.
                page_text = page.get_text("text")

                # Ignoramos páginas vacías (por ejemplo, páginas de portada
                # que solo tienen una imagen sin texto seleccionable).
                if page_text.strip():
                    # Añadimos un marcador de página para facilitar el debug
                    # y para que el chunker (Step 5) pueda usar los saltos
                    # como señales naturales de separación si lo necesita.
                    pages_text.append(f"--- Page {page_number} ---\n{page_text}")

            # --- Validación 3: ¿Se extrajo algo? ---
            # Un PDF sin texto seleccionable (PDF escaneado = imagen)
            # no lanza error en fitz, simplemente devuelve strings vacíos.
            # Lo detectamos aquí y lo comunicamos explícitamente.
            if not pages_text:
                raise ExtractionError(
                    "No selectable text found in the PDF. "
                    "The document may be a scanned image and would require OCR."
                )

            # Unimos todas las páginas con un doble salto de línea.
            # Esto preserva la estructura del documento.
            full_text = "\n\n".join(pages_text)
            
            # Limpieza crítica: PostgreSQL no soporta el caracter nulo (0x00)
            # en columnas de texto. Los PDFs generados por OCR o con fuentes
            # extrañas suelen incluirlo. Lo removemos antes de devolver el texto.
            full_text = full_text.replace("\x00", "")
            
            return full_text

    except ExtractionError:
        # Re-lanzamos nuestras propias excepciones sin modificarlas.
        raise

    except fitz.FileDataError as e:
        # fitz lanza este error específico cuando el archivo PDF está corrupto
        # o no es un PDF válido (aunque tenga extensión .pdf).
        raise ExtractionError(f"Invalid or corrupted PDF file: {e}") from e

    except Exception as e:
        # Capturamos cualquier otro error inesperado de fitz y lo envolvemos
        # en nuestra excepción para que el service no tenga que conocer
        # los detalles internos de la librería de extracción.
        raise ExtractionError(f"Failed to extract text from PDF: {e}") from e
