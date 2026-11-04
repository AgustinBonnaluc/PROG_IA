# Planificador de cortes - version planta
# Arma el plan de corte de barras para las OT pendientes.
# Uso: python corte_manual.py

# datos de las OT pendientes (copiados de la planilla de produccion)
# formato: (OT, material, descripcion, largo en mm, cantidad)
datos = [
    ("OT-101", "CE-40x40x1.6", "Pata estanteria", 2000, 4),
    ("OT-101", "CE-40x40x1.6", "Travesano estanteria", 1450, 6),
    ("OT-101", "ANG-1.1/4x1/8", "Refuerzo estante", 1150, 5),
    ("OT-102", "CE-40x40x1.6", "Larguero mesa", 1500, 4),
    ("OT-102", "CE-40x40x1.6", "Pata mesa", 900, 4),
    ("OT-102", "CE-40x40x1.6", "Cabezal mesa", 700, 2),
    ("OT-103", "CE-40x40x1.6", "Parante porton", 3100, 2),
    ("OT-103", "CE-40x40x1.6", "Travesano porton", 2800, 3),
    ("OT-103", "PLA-2x3/16", "Planchuela bisagra", 250, 6),
    ("OT-104", "ANG-1.1/4x1/8", "Marco reja", 1200, 5),
    ("OT-104", "ANG-1.1/4x1/8", "Lateral reja", 1950, 2),
    ("OT-105", "PLA-2x3/16", "Pasamanos", 2990, 4),
    ("OT-105", "PLA-2x3/16", "Soporte pasamanos", 380, 6),
    ("OT-106", "CE-40x40x1.6", "Bastidor soporte AA", 800, 2),
    ("OT-106", "ANG-1.1/4x1/8", "Mensula soporte AA", 600, 4),
    ("OT-107", "ANG-1.1/4x1/8", "Marco rejilla", 450, 6),
    ("OT-107", "PLA-2x3/16", "Lama rejilla", 500, 4),
]

barras = []


def planificar():
    global barras
    barras = []
    ots = []
    for d in datos:
        if d[0] not in ots:
            ots.append(d[0])
    for ot in ots:
        mats = []
        for d in datos:
            if d[0] == ot and d[1] not in mats:
                mats.append(d[1])
        for m in mats:
            b = []
            l = 6000
            for d in datos:
                if d[0] == ot and d[1] == m:
                    for i in range(d[4]):
                        # si entra en la barra actual la corto ahi, si no abro otra
                        # TODO: el ancho de la sierra lo maneja el operario en el taller
                        if d[3] <= l:
                            b.append(d[3])
                            l = l - d[3]
                        else:
                            barras.append([ot, m, b])
                            b = [d[3]]
                            l = 6000 - d[3]
            barras.append([ot, m, b])
    tot = 0
    usado = 0
    print("=" * 60)
    print("PLAN DE CORTE")
    print("=" * 60)
    n = 1
    for x in barras:
        s = 0
        for p in x[2]:
            s = s + p
        print("Barra", n, "|", x[0], "|", x[1], "|", x[2], "| sobra", 6000 - s, "mm")
        tot = tot + 6000
        usado = usado + s
        n = n + 1
    print("-" * 60)
    print("Barras usadas:", len(barras))
    print("Desperdicio total:", tot - usado, "mm")
    print("Aprovechamiento:", round(usado / tot * 100, 1), "%")


planificar()
