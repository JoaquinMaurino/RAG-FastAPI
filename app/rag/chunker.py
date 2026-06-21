"""
Step 5: Chunking — División del texto en fragmentos manejables.

Responsabilidad única: dado un string de texto, devolver una lista
de strings (chunks) de tamaño controlado y con overlap entre ellos.

¿Por qué está en app/rag/ y no en app/services/?
-------------------------------------------------
Mismo razonamiento que extractor.py: es una función de transformación
pura. Input → Output. Sin efectos secundarios.

    input:  string de texto (puede ser 500.000 caracteres)
    output: lista de strings (cada uno ≤ chunk_size caracteres)

Los services orquestan. El chunker es la herramienta.

Algoritmo: Recursive Character Text Splitter
--------------------------------------------
Es la estrategia estándar en producción (la misma que usa LangChain
internamente, la implementamos nosotros para entenderla desde cero).

Funciona así:
1. Intentar cortar por \n\n (separador semántico más fuerte: párrafos)
2. Si el fragmento resultante sigue siendo demasiado grande:
   → intentar con \n (saltos de línea simples)
3. Si sigue siendo muy grande:
   → intentar con ". " (oraciones)
4. Si sigue siendo muy grande:
   → cortar por " " (palabras)
5. Último recurso: cortar carácter por carácter

En cada nivel se agrupa lo máximo posible dentro de chunk_size,
y al iniciar cada nuevo chunk se "reciclan" los últimos chunk_overlap
caracteres del chunk anterior (eso es el overlap).

¿Para qué sirve el overlap?
----------------------------
Sin overlap:

    Chunk 1: "...La empresa fue fundada en 1990 y su primer"
    Chunk 2: "producto fue el modelo X, que revolucionó..."

El contexto "primer producto" está partido entre dos chunks. Si el
usuario pregunta "¿cuál fue el primer producto?", el retriever podría
traer solo el Chunk 2 que no tiene suficiente contexto.

Con overlap (los últimos 200 chars del Chunk 1 se copian al inicio del Chunk 2):

    Chunk 1: "...La empresa fue fundada en 1990 y su primer"
    Chunk 2: "su primer producto fue el modelo X, que revolucionó..."

Ahora cualquiera de los dos chunks tiene el contexto suficiente.
"""

# Parámetros por defecto (ajustables para experimentar)
# -------------------------------------------------------
# chunk_size: 1000 chars ≈ ~200 palabras ≈ ~3-5 oraciones.
#   Lo suficientemente grande para tener contexto,
#   lo suficientemente pequeño para ser preciso en la búsqueda.
#
# chunk_overlap: 200 chars ≈ ~40 palabras.
#   Aproximadamente el 20% del chunk_size. Regla empírica común.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

# Separadores en orden de prioridad (de más semántico a más granular).
# El algoritmo los recorre de izquierda a derecha.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Divide un texto en chunks de tamaño controlado con overlap.

    Es la función pública del módulo. Delega en _split_recursively()
    que contiene la lógica recursiva.

    Args:
        text:          El texto completo a dividir (raw_text del documento).
        chunk_size:    Tamaño máximo de cada chunk en caracteres.
        chunk_overlap: Cantidad de caracteres compartidos entre chunks consecutivos.

    Returns:
        Lista de strings. Cada string es un chunk listo para ser
        embebido y almacenado en la base de datos.

    Ejemplo:
        >>> chunks = chunk_text("texto muy largo...", chunk_size=500, chunk_overlap=100)
        >>> len(chunks)
        12
        >>> len(chunks[0])
        487
    """
    if not text or not text.strip():
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be smaller than "
            f"chunk_size ({chunk_size})"
        )

    chunks = _split_recursively(text.strip(), chunk_size, chunk_overlap, SEPARATORS)

    # Filtramos chunks que quedaron vacíos o con solo espacios
    # (puede pasar si el texto tiene muchos saltos de línea consecutivos)
    return [c for c in chunks if c.strip()]


def _split_recursively(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str],
) -> list[str]:
    """
    Función interna recursiva. No llamar directamente desde fuera del módulo.

    Elige el mejor separador disponible, divide el texto por ese separador,
    agrupa los fragmentos en chunks respetando chunk_size, y aplica overlap.

    Si algún fragmento sigue siendo mayor que chunk_size después de dividir,
    se llama recursivamente con el siguiente separador (más granular).

    Args:
        text:       Texto a dividir.
        chunk_size: Tamaño máximo del chunk.
        chunk_overlap: Overlap en caracteres.
        separators: Lista de separadores disponibles en orden de prioridad.

    Returns:
        Lista de chunks de texto.
    """
    # --- Paso 1: Elegir el separador ---
    # Recorremos los separadores en orden de prioridad y elegimos el primero
    # que realmente aparezca en el texto. Así usamos siempre el más semántico
    # posible dado el contenido actual.
    chosen_separator = separators[-1]   # fallback: string vacío (char por char)
    remaining_separators = []

    for i, sep in enumerate(separators):
        if sep == "" or sep in text:
            chosen_separator = sep
            # Los separadores más granulares quedan disponibles para recursión
            remaining_separators = separators[i + 1:]
            break

    # --- Paso 2: Dividir por el separador elegido ---
    # Si el separador es "", split("") en Python no hace lo que esperamos,
    # así que usamos list() para obtener caracteres individuales.
    if chosen_separator:
        splits = text.split(chosen_separator)
    else:
        splits = list(text)

    # --- Paso 3: Agrupar fragmentos en chunks ---
    # Iteramos los fragmentos y los vamos acumulando hasta llegar a chunk_size.
    # Cuando superamos el límite, cerramos el chunk actual y empezamos uno nuevo
    # con el overlap del anterior.
    chunks: list[str] = []
    current_parts: list[str] = []   # fragmentos acumulados para el chunk actual
    current_length: int = 0         # longitud total del chunk en construcción

    for split in splits:
        split_len = len(split)
        # Longitud extra que agrega el separador al unir las partes
        separator_overhead = len(chosen_separator) * len(current_parts)
        total_if_added = current_length + separator_overhead + split_len

        if total_if_added <= chunk_size:
            # El fragmento cabe → lo acumulamos
            current_parts.append(split)
            current_length += split_len
        else:
            # El fragmento no cabe → cerramos el chunk actual
            if current_parts:
                chunk = chosen_separator.join(current_parts).strip()

                if chunk:
                    # Si el chunk formado sigue siendo mayor que chunk_size
                    # y tenemos separadores más granulares disponibles,
                    # dividimos recursivamente en vez de guardar un chunk gigante.
                    if len(chunk) > chunk_size and remaining_separators:
                        sub_chunks = _split_recursively(
                            chunk, chunk_size, chunk_overlap, remaining_separators
                        )
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append(chunk)

                # --- Overlap ---
                # Reconstruimos current_parts conservando los últimos fragmentos
                # que sumen hasta chunk_overlap caracteres. Estos fragmentos
                # "se copian" al inicio del siguiente chunk.
                current_parts, current_length = _apply_overlap(
                    current_parts, chunk_overlap
                )

            # Agregamos el fragmento actual al nuevo chunk (que ya tiene el overlap)
            current_parts.append(split)
            current_length += split_len

    # --- Paso 4: No olvidar el último chunk ---
    if current_parts:
        chunk = chosen_separator.join(current_parts).strip()
        if chunk:
            if len(chunk) > chunk_size and remaining_separators:
                sub_chunks = _split_recursively(
                    chunk, chunk_size, chunk_overlap, remaining_separators
                )
                chunks.extend(sub_chunks)
            else:
                chunks.append(chunk)

    return chunks


def _apply_overlap(
    parts: list[str],
    chunk_overlap: int,
) -> tuple[list[str], int]:
    """
    Calcula qué fragmentos del chunk recién cerrado se deben conservar
    para el inicio del próximo chunk (el overlap).

    Recorre las partes de atrás hacia adelante y las acumula hasta
    llegar a chunk_overlap caracteres.

    Args:
        parts:         Fragmentos del chunk recién cerrado.
        chunk_overlap: Cantidad máxima de caracteres a conservar.

    Returns:
        Tupla (partes_a_conservar, longitud_total_de_esas_partes).
    """
    overlap_parts: list[str] = []
    overlap_length: int = 0

    for part in reversed(parts):
        if overlap_length + len(part) <= chunk_overlap:
            overlap_parts.insert(0, part)
            overlap_length += len(part)
        else:
            # Este fragmento haría superar el overlap → detenemos
            break

    return overlap_parts, overlap_length
