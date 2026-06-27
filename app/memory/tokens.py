"""
Helper para cálculo aproximado de tokens.
"""

def approx_tokens(text: str) -> int:
    """
    Aproximación barata de cantidad de tokens.
    Evita una llamada de red a la API de Gemini (count_tokens) 
    o el overhead de inicializar tiktoken por cada request.
    
    Regla general: 1 token ≈ 4 caracteres en inglés.
    """
    if not text:
        return 0
    return len(text) // 4
