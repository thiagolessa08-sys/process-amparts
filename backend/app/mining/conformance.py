"""Checa se uma sequência de atividades conforma com o processo-ideal."""


def is_conformant(sequence: list[str], ideal: list[str]) -> bool:
    """Retorna True se 'sequence' contém todas as atividades de 'ideal'
    na mesma ordem relativa (subsequência), sem atividades extras
    que não estejam no ideal."""
    ideal_set = set(ideal)
    filtered = [a for a in sequence if a in ideal_set]
    return filtered == ideal
