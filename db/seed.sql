-- =====================================================================
-- Seed de la base de la metalúrgica (caso hipotético, datos ficticios)
-- Ejecutar completo en el SQL Editor de Supabase. Es idempotente:
-- se puede volver a correr para resetear la demo.
--
-- Cambios respecto del Parcial 1:
--   * ordenes_trabajo registra el origen de la OT (planilla o agente) y el
--     mensaje original del cliente, para auditar lo que ingresó el agente.
--   * planes_corte y cortes ya no los crea el LLM en vivo: forman parte del
--     esquema y los escribe el código del agente con consultas parametrizadas.
-- =====================================================================

-- Reset
drop table if exists cortes cascade;
drop table if exists planes_corte cascade;
drop table if exists piezas cascade;
drop table if exists ordenes_trabajo cascade;
drop table if exists materiales cascade;
drop table if exists parametros_planta cascade;

-- ---------------------------------------------------------------------
-- Esquema
-- ---------------------------------------------------------------------
create table materiales (
    id              bigint generated always as identity primary key,
    codigo          text          not null unique,
    descripcion     text          not null,
    largo_barra_mm  integer       not null check (largo_barra_mm > 0),
    kg_por_metro    numeric(6, 3) not null check (kg_por_metro > 0)
);

create table ordenes_trabajo (
    id                bigint generated always as identity primary key,
    codigo            text not null unique,
    cliente           text not null check (length(cliente) between 1 and 120),
    descripcion       text not null,
    fecha_entrega     date not null,
    estado            text not null default 'pendiente'
                      check (estado in ('pendiente', 'planificada', 'en_produccion', 'entregada')),
    origen            text not null default 'planilla'
                      check (origen in ('planilla', 'agente')),
    mensaje_original  text check (length(mensaje_original) <= 2000),
    creada_en         timestamptz not null default now()
);

create table piezas (
    id           bigint generated always as identity primary key,
    orden_id     bigint  not null references ordenes_trabajo (id) on delete cascade,
    material_id  bigint  not null references materiales (id),
    descripcion  text    not null,
    largo_mm     integer not null check (largo_mm > 0),
    cantidad     integer not null check (cantidad between 1 and 500)
);

create index idx_piezas_orden on piezas (orden_id);
create index idx_piezas_material on piezas (material_id);

create table parametros_planta (
    clave        text    primary key,
    valor        numeric not null,
    descripcion  text    not null
);

-- Un plan vigente por material. Guarda también cómo estaba antes del último
-- recálculo, para que el panel muestre el impacto de cada OT nueva.
create table planes_corte (
    id                     bigint generated always as identity primary key,
    material_id            bigint        not null unique references materiales (id),
    fecha                  timestamptz   not null default now(),
    motivo                 text          not null,
    barras_usadas          integer       not null check (barras_usadas >= 0),
    desperdicio_mm         numeric(10,1) not null check (desperdicio_mm >= 0),
    aprovechamiento_pct    numeric(5,1)  not null,
    cota_inferior          integer       not null,
    barras_antes           integer,
    aprovechamiento_antes  numeric(5,1)
);

create table cortes (
    id         bigint generated always as identity primary key,
    plan_id    bigint  not null references planes_corte (id) on delete cascade,
    nro_barra  integer not null,
    posicion   integer not null,
    largo_mm   integer not null,
    pieza_id   bigint  not null references piezas (id) on delete cascade
);

create index idx_cortes_plan on cortes (plan_id);

-- RLS activado sin políticas: bloquea el acceso público vía API REST.
-- El agente y el panel se conectan por Postgres con la cadena del .env.
alter table materiales        enable row level security;
alter table ordenes_trabajo   enable row level security;
alter table piezas            enable row level security;
alter table parametros_planta enable row level security;
alter table planes_corte      enable row level security;
alter table cortes            enable row level security;

-- ---------------------------------------------------------------------
-- Datos
-- kg_por_metro aproximado a partir de la geometría del perfil
-- (densidad del acero 7,85 g/cm³)
-- ---------------------------------------------------------------------
insert into materiales (codigo, descripcion, largo_barra_mm, kg_por_metro) values
    ('CE-40x40x1.6',  'Caño estructural cuadrado 40x40x1,6 mm', 6000, 1.930),
    ('ANG-1.1/4x1/8', 'Hierro ángulo 1 1/4" x 1/8"',            6000, 1.503),
    ('PLA-2x3/16',    'Planchuela 2" x 3/16"',                  6000, 1.899);

insert into parametros_planta (clave, valor, descripcion) values
    ('kerf_mm', 3, 'Ancho de corte de la sierra sin fin. Cada pieza consume su largo más este valor.');

-- Fechas relativas al día de ejecución para que la demo nunca quede desactualizada
insert into ordenes_trabajo (codigo, cliente, descripcion, fecha_entrega, estado) values
    ('OT-100', 'Herrería Del Parque',       'Escalera caracol (entregada, no debe planificarse)', current_date - 10, 'entregada'),
    ('OT-101', 'Depósitos del Sur SA',      'Estantería para depósito',                           current_date + 6,  'pendiente'),
    ('OT-102', 'Taller Mecánico Ferraro',   'Mesa de trabajo reforzada',                          current_date + 4,  'pendiente'),
    ('OT-103', 'Consorcio Las Acacias',     'Portón corredizo de acceso',                         current_date + 9,  'pendiente'),
    ('OT-104', 'Familia Iturralde',         'Reja para ventana',                                  current_date + 5,  'pendiente'),
    ('OT-105', 'Colegio Nuevo Horizonte',   'Baranda para escalera',                              current_date + 12, 'pendiente'),
    ('OT-106', 'Clima Integral SRL',        'Soporte para equipo de aire acondicionado',          current_date + 3,  'pendiente'),
    ('OT-107', 'Panificadora La Espiga',    'Rejilla de ventilación',                             current_date + 7,  'pendiente');

-- Piezas en el mismo orden en que figuran en la planilla de producción
insert into piezas (orden_id, material_id, descripcion, largo_mm, cantidad)
select o.id, m.id, v.descripcion, v.largo_mm, v.cantidad
from (values
    ( 1, 'OT-100', 'CE-40x40x1.6',  'Escalón escalera',     900, 8),
    ( 2, 'OT-101', 'CE-40x40x1.6',  'Pata estantería',     2000, 4),
    ( 3, 'OT-101', 'CE-40x40x1.6',  'Travesaño estantería',1450, 6),
    ( 4, 'OT-101', 'ANG-1.1/4x1/8', 'Refuerzo estante',    1150, 5),
    ( 5, 'OT-102', 'CE-40x40x1.6',  'Larguero mesa',       1500, 4),
    ( 6, 'OT-102', 'CE-40x40x1.6',  'Pata mesa',            900, 4),
    ( 7, 'OT-102', 'CE-40x40x1.6',  'Cabezal mesa',         700, 2),
    ( 8, 'OT-103', 'CE-40x40x1.6',  'Parante portón',      3100, 2),
    ( 9, 'OT-103', 'CE-40x40x1.6',  'Travesaño portón',    2800, 3),
    (10, 'OT-103', 'PLA-2x3/16',    'Planchuela bisagra',   250, 6),
    (11, 'OT-104', 'ANG-1.1/4x1/8', 'Marco reja',          1200, 5),
    (12, 'OT-104', 'ANG-1.1/4x1/8', 'Lateral reja',        1950, 2),
    (13, 'OT-105', 'PLA-2x3/16',    'Pasamanos',           2990, 4),
    (14, 'OT-105', 'PLA-2x3/16',    'Soporte pasamanos',    380, 6),
    (15, 'OT-106', 'CE-40x40x1.6',  'Bastidor soporte AA',  800, 2),
    (16, 'OT-106', 'ANG-1.1/4x1/8', 'Ménsula soporte AA',   600, 4),
    (17, 'OT-107', 'ANG-1.1/4x1/8', 'Marco rejilla',        450, 6),
    (18, 'OT-107', 'PLA-2x3/16',    'Lama rejilla',         500, 4)
) as v (orden, ot, material, descripcion, largo_mm, cantidad)
join ordenes_trabajo o on o.codigo = v.ot
join materiales m on m.codigo = v.material
order by v.orden;

-- ---------------------------------------------------------------------
-- Verificación rápida: 3 filas (una por material). Totales esperados:
-- ANG 22 piezas / 20750 mm · CE 27 piezas / 43900 mm · PLA 20 piezas / 17740 mm
-- ---------------------------------------------------------------------
select m.codigo                          as material,
       count(distinct o.id)              as ot_pendientes,
       sum(p.cantidad)                   as piezas,
       sum(p.cantidad * p.largo_mm)      as mm_requeridos
from piezas p
join ordenes_trabajo o on o.id = p.orden_id
join materiales m on m.id = p.material_id
where o.estado = 'pendiente'
group by m.codigo
order by m.codigo;
