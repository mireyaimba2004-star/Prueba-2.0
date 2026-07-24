# -*- coding: utf-8 -*-
"""
Planificación Estratégica Interactiva
======================================
App de Streamlit que reconstruye el libro de Excel de planificación estratégica
(caso empresa exportadora de flores) en 8 matrices editables:

1. Matriz Holmes / MICMAC (motricidad-dependencia de Fortalezas, Debilidades,
   Amenazas y Oportunidades)
2. EFI  - Evaluación de Factores Internos
3. EFE  - Evaluación de Factores Externos
4. Cadena de Valor
5. Matriz de Perfil Competitivo (MPC)
6. Matriz ASSNOF / Ansoff
7. Matriz de Riesgos
8. FODA Numérico (cruce cuantitativo F/D vs O/A)

Cada pestaña permite editar los valores "movibles" (pesos, calificaciones,
puntajes de impacto, probabilidad/consecuencia, etc.), recalcula automáticamente
los totales/derivados y agrega una interpretación en lenguaje natural que
cambia según los valores introducidos.
"""

import json
import os

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ------------------------------------------------------------------
# Configuración general
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Planificación Estratégica Interactiva",
    layout="wide",
    page_icon="📊",
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def load_json(name):
    with open(os.path.join(DATA_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def init_state(key, loader):
    """Carga datos por defecto en session_state una sola vez (deep copy)."""
    if key not in st.session_state:
        st.session_state[key] = json.loads(json.dumps(loader()))
    return st.session_state[key]


def _purge_widget_state(widget_keys):
    """Borra de session_state cualquier clave de widget (data_editor, text_input, etc.)
    que coincida exactamente o empiece con alguno de los prefijos indicados.

    Streamlit conserva el valor interno de un widget con key= aunque el dato fuente
    (session_state[key] del formulario) cambie -- por eso el botón 'Restaurar valores
    originales' no se reflejaba visualmente: se reseteaba el dato pero no el widget.
    """
    if not widget_keys:
        return
    existentes = list(st.session_state.keys())
    for wk in widget_keys:
        for sk in existentes:
            if sk == wk or sk.startswith(wk):
                del st.session_state[sk]


def reset_button(key, loader, widget_keys=None, label="↩️ Restaurar valores originales", button_key=None):
    """widget_keys: lista de claves exactas o prefijos (para claves dinámicas tipo
    f'algo_{i}') de los widgets que dependen de este dato y deben limpiarse para
    que el reset se vea reflejado en pantalla.
    button_key: permite tener varios botones de reset sobre el MISMO dato (key) en
    pestañas distintas, sin que Streamlit se queje de claves duplicadas."""
    if st.button(label, key=f"reset_{button_key or key}"):
        st.session_state[key] = json.loads(json.dumps(loader()))
        _purge_widget_state(widget_keys)
        st.rerun()


NUM_COL = st.column_config.NumberColumn

# ====================================================================
# REGISTRO MAESTRO DE FACTORES (F1-F11, D1-D11)
# ----------------------------------------------------------------------
# Holmes/MICMAC, EFI y FODA Numérico usan los MISMOS factores internos
# (fortalezas F1-F11 y debilidades D1-D11); antes cada matriz guardaba su
# propia copia del texto, así que renombrar un factor en un lado no se
# reflejaba en los demás. Ahora el nombre vive en un solo lugar
# (data/factores_maestro.json) y las tres matrices lo consultan por código.
# ====================================================================

def get_master_factors():
    return init_state("factores_maestro", lambda: load_json("factores_maestro"))


def factor_nombre(tipo, codigo):
    """tipo: 'F' o 'D'. Devuelve el nombre vigente del factor (editable desde
    Holmes o EFI, y visible también en FODA Numérico)."""
    reg = get_master_factors()
    for f in reg.get(tipo, []):
        if f["codigo"] == codigo:
            return f["nombre"]
    return codigo


def set_factor_nombre(tipo, codigo, nuevo_nombre):
    reg = get_master_factors()
    for f in reg.get(tipo, []):
        if f["codigo"] == codigo:
            f["nombre"] = nuevo_nombre
            return


def factor_calificacion(fuente, codigo):
    """Calificación (1-4) vigente de un factor de EFI o EFE. Se usa para que
    matrices que dependen de estos factores (ej. Cadena de Valor) se
    recalculen automáticamente cuando cambia la calificación en EFI/EFE."""
    if fuente == "EFI":
        efi = init_state("efi", lambda: load_json("efi"))
        for grupo in ("fortalezas", "debilidades"):
            for f in efi.get(grupo, []):
                if f["codigo"] == codigo:
                    return f["calificacion"]
    elif fuente == "EFE":
        efe = init_state("efe", lambda: load_json("efe"))
        for grupo in ("oportunidades", "amenazas"):
            for f in efe.get(grupo, []):
                if f.get("codigo") == codigo:
                    return f["calificacion"]
    return None


def factor_display_nombre(fuente, codigo):
    """Nombre legible de un factor de EFI (vía registro maestro F/D) o de EFE
    (el propio texto del factor), para mostrar de dónde viene un vínculo."""
    if fuente == "EFI":
        tipo = "F" if codigo.startswith("F") else "D"
        return factor_nombre(tipo, codigo)
    if fuente == "EFE":
        efe = init_state("efe", lambda: load_json("efe"))
        for grupo in ("oportunidades", "amenazas"):
            for f in efe.get(grupo, []):
                if f.get("codigo") == codigo:
                    return f["factor"]
    return codigo


def clasificar_bmm(valor, umbral_bueno, umbral_medio, invertido=False):
    """Clasifica un valor numérico en 🟢 Bueno / 🟡 Medio / 🔴 Malo según dos umbrales.
    invertido=True cuando un valor MÁS BAJO es mejor (ej. escalas de riesgo)."""
    if invertido:
        if valor <= umbral_bueno:
            return "🟢 Bueno"
        elif valor <= umbral_medio:
            return "🟡 Medio"
        return "🔴 Malo"
    if valor >= umbral_bueno:
        return "🟢 Bueno"
    elif valor >= umbral_medio:
        return "🟡 Medio"
    return "🔴 Malo"


def objetivo_texto(objetivo_id, fallback=""):
    """Texto vigente de un Objetivo Estratégico (OE1/OE2/OE3), tomado siempre
    de la pestaña 🏁 Objetivos. Mapa Estratégico, CMI Oficial y Cuadro de
    Mando lo consultan por id en vez de guardar su propia copia del texto."""
    if not objetivo_id:
        return fallback
    objetivos = init_state("objetivos", lambda: load_json("objetivos"))
    for oe in objetivos.get("objetivos_estrategicos", []):
        if oe.get("id") == objetivo_id:
            return oe["texto"]
    return fallback

# ====================================================================
# 0. CARÁTULA
# ====================================================================

def tab_caratula():
    data = init_state("caratula", lambda: load_json("caratula"))

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            lc1, lc2, lc3 = st.columns([1, 1, 1])
            with lc2:
                st.image(logo_path, use_container_width=True)

        st.markdown(
            f"<h1 style='text-align:center;margin-top:0.5em;'>{data['nombre_comercial']}</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<h4 style='text-align:center;color:#666;font-weight:400;'>{data['subtitulo']}</h4>",
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            fields = [
                ("Razón social", "razon_social"),
                ("Nombre comercial", "nombre_comercial"),
                ("RUC", "ruc"),
                ("Tipo de compañía", "tipo_compania"),
                ("Fecha de constitución", "constitucion"),
                ("Ubicación", "ubicacion"),
                ("Actividad económica principal", "actividad_economica"),
            ]
            edited = {}
            for label, key in fields:
                edited[key] = st.text_input(label, value=data[key], key=f"caratula_{key}")
            st.session_state["caratula"].update(edited)

        st.markdown("<br>", unsafe_allow_html=True)
        bc1, bc2, bc3 = st.columns([1, 1.3, 1])
        with bc2:
            if st.button("➡️  Avanzar al módulo de Planificación Estratégica", use_container_width=True, type="primary"):
                st.session_state["page"] = "modulo"
                st.rerun()


# ====================================================================
# A. PROBLEMÁTICA
# ====================================================================

def tab_problematica():
    st.header("❗ Problemática")
    data = init_state("problematica", lambda: load_json("problematica"))
    reset_button("problematica", lambda: load_json("problematica"),
                  widget_keys=["prob_titulo", "prob_texto"])

    titulo = st.text_input("Enunciado central de la problemática", value=data["titulo"], key="prob_titulo")
    texto = st.text_area("Desarrollo de la problemática", value=data["texto"], height=260, key="prob_texto")
    st.session_state["problematica"]["titulo"] = titulo
    st.session_state["problematica"]["texto"] = texto

    st.subheader("🧭 Interpretación")
    n_palabras = len(texto.split())
    st.markdown(
        f"La problemática identificada — **{titulo}** — describe una brecha entre la "
        f"sofisticación operativa/tecnológica de la organización y la madurez de su marco "
        f"normativo interno (políticas, principios y valores). Este desbalance es el punto de "
        f"partida que justifica formalizar la misión, visión, objetivos, políticas, valores y "
        f"principios que se desarrollan en las siguientes pestañas."
    )
    st.caption(f"Extensión actual del texto: {n_palabras} palabras.")


# ====================================================================
# B. MISIÓN Y VISIÓN
# ====================================================================

def tab_mision_vision():
    st.header("🎯 Misión y Visión")
    data = init_state("mision_vision", lambda: load_json("mision_vision"))
    reset_button("mision_vision", lambda: load_json("mision_vision"),
                  widget_keys=["mv_mo", "mv_mp", "mv_me", "mv_vo", "mv_vp", "mv_ve"])

    st.subheader("Misión")
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Misión declarada por la empresa**")
        mo = st.text_area("Misión original", value=data["mision_original"], height=200,
                           key="mv_mo", label_visibility="collapsed")
    with m2:
        st.markdown("**Misión propuesta (mejorada)**")
        mp = st.text_area("Misión propuesta", value=data["mision_propuesta"], height=200,
                           key="mv_mp", label_visibility="collapsed")
    me = st.text_area("Evaluación estratégica de la misión", value=data["mision_evaluacion"],
                       height=110, key="mv_me")

    st.divider()
    st.subheader("Visión")
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("**Visión declarada por la empresa**")
        vo = st.text_area("Visión original", value=data["vision_original"], height=200,
                           key="mv_vo", label_visibility="collapsed")
    with v2:
        st.markdown("**Visión propuesta (mejorada)**")
        vp = st.text_area("Visión propuesta", value=data["vision_propuesta"], height=200,
                           key="mv_vp", label_visibility="collapsed")
    ve = st.text_area("Evaluación estratégica de la visión", value=data["vision_evaluacion"],
                       height=110, key="mv_ve")

    st.session_state["mision_vision"].update({
        "mision_original": mo, "mision_propuesta": mp, "mision_evaluacion": me,
        "vision_original": vo, "vision_propuesta": vp, "vision_evaluacion": ve,
    })

    st.subheader("🧭 Interpretación")
    len_mo, len_mp = len(mo.split()), len(mp.split())
    len_vo, len_vp = len(vo.split()), len(vp.split())
    st.markdown(
        f"- La misión propuesta tiene **{len_mp} palabras** frente a las **{len_mo}** de la "
        "versión original: " + (
            "es más concisa y por tanto potencialmente más memorable y accionable."
            if len_mp < len_mo else
            "amplía el enunciado original para precisar mejor su alcance."
        )
    )
    st.markdown(
        f"- La visión propuesta fija un **horizonte temporal explícito (2031)**, algo que la "
        "declaración original no especifica — esto facilita medir el avance estratégico y alinear "
        "los objetivos con una fecha límite concreta."
    )


# ====================================================================
# C. OBJETIVOS (con ponderación)
# ====================================================================

def _editable_factor_table(factores, key_prefix):
    """Tabla editable Factor|Peso|Importancia(1-4); calcula Valor=Peso*Importancia y %.
    Devuelve (df_editado_con_calculos, lista_de_dicts_para_guardar)."""
    df = pd.DataFrame(factores)[["factor", "peso", "importancia"]]
    edited = st.data_editor(
        df,
        key=key_prefix,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "factor": st.column_config.TextColumn("Factor", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "importancia": st.column_config.SelectboxColumn("Importancia (1-4)", options=[1, 2, 3, 4]),
        },
    )
    edited = edited.assign(
        valor=edited["peso"] * edited["importancia"],
        porcentaje=edited["peso"] * 100,
    )
    return edited, edited[["factor", "peso", "importancia"]].to_dict("records")


def tab_objetivos():
    st.header("🏁 Objetivos Estratégicos")
    st.caption(
        "La ponderación se calcula en **cascada**: cada Factor tiene un Peso e Importancia (1-4) → "
        "de ahí sale su Valor y su % → los % de los factores de un Objetivo Táctico se combinan en "
        "un Valor Total → ese Valor Total, comparado entre los 3 tácticos de un mismo Objetivo "
        "Estratégico, define el **peso relativo** de cada táctico → y ese peso relativo, aplicado "
        "sobre el % que el Objetivo Estratégico aporta a la misión, da la **Contribución real** de "
        "cada objetivo táctico. Mueve cualquier Peso o Importancia y todo se recalcula automáticamente."
    )

    data = init_state("objetivos", lambda: load_json("objetivos"))
    reset_button("objetivos", lambda: load_json("objetivos"),
                  widget_keys=["editor_ponderacion", "obj_eje_", "obj_texto_",
                               "oe_factores_", "tac_texto_", "tac_factores_"])

    # ------------------------------------------------------------------
    # 1) Ponderación de Objetivos Estratégicos frente a la misión
    # ------------------------------------------------------------------
    st.subheader("📊 1. Ponderación de los Objetivos Estratégicos frente a la misión")
    df_pond = pd.DataFrame(data["ponderacion"])
    edited_pond = st.data_editor(
        df_pond[["objetivo", "porcentaje", "formula"]],
        key="editor_ponderacion", num_rows="dynamic", use_container_width=True,
        column_config={
            "objetivo": st.column_config.TextColumn("Objetivo estratégico", width="large"),
            "porcentaje": NUM_COL("% de cumplimiento de la misión", min_value=0, max_value=100, step=1),
            "formula": st.column_config.TextColumn("Fórmula / indicador", width="large"),
        },
        height=180,
    )
    st.session_state["objetivos"]["ponderacion"] = edited_pond.to_dict("records")
    oe_pct = edited_pond["porcentaje"].tolist()  # % de cada OE en el mismo orden que objetivos_estrategicos

    total_pct = edited_pond["porcentaje"].sum()
    c1, c2 = st.columns(2)
    c1.metric("Suma de ponderaciones", f"{total_pct:.0f}%")
    top_obj = edited_pond.sort_values("porcentaje", ascending=False).iloc[0]
    c2.metric("Objetivo de mayor peso", f"{top_obj['porcentaje']:.0f}%")
    if total_pct > 100:
        st.caption(
            f"ℹ️ La suma es {total_pct:.0f}% porque cada objetivo se pondera de forma independiente "
            "frente a la misión (no es una distribución que deba sumar 100%), igual que en el "
            "documento fuente."
        )

    st.divider()

    # ------------------------------------------------------------------
    # 2) Detalle en cascada por cada Objetivo Estratégico
    # ------------------------------------------------------------------
    st.subheader("🧩 2. Detalle de cada Objetivo Estratégico (factores → tácticos)")

    resumen_oe_rows = []

    for i, obj in enumerate(data["objetivos_estrategicos"]):
        oe_peso_mision = oe_pct[i] if i < len(oe_pct) else 0
        with st.expander(f"**{obj['titulo']}** — {obj['eje']}  ·  {oe_peso_mision:.0f}% de la misión",
                          expanded=(i == 0)):

            eje = st.text_input("Eje estratégico", value=obj["eje"], key=f"obj_eje_{i}")
            texto = st.text_area("Enunciado del objetivo estratégico", value=obj["texto"],
                                  height=90, key=f"obj_texto_{i}")

            st.markdown("**Factores que componen este Objetivo Estratégico:**")
            edited_oe_factores, oe_factores_guardar = _editable_factor_table(
                obj["factores"], key_prefix=f"oe_factores_{i}"
            )
            peso_oe_total = edited_oe_factores["peso"].sum()
            if abs(peso_oe_total - 1.0) > 0.01:
                st.caption(f"⚠️ Los pesos de los factores suman {peso_oe_total:.2f} (debería ser 1.00).")
            top_factor_oe = edited_oe_factores.sort_values("valor", ascending=False).iloc[0]
            st.caption(
                f"👉 El factor de mayor peso es **{top_factor_oe['factor']}** "
                f"({top_factor_oe['porcentaje']:.0f}%, valor {top_factor_oe['valor']:.2f})."
            )

            st.markdown("---")
            st.markdown("**Objetivos tácticos** (cada uno con su propia matriz de factores):")

            valor_total_tacticos = []
            tacticos_guardar = []
            for j, tac in enumerate(obj["tacticos"]):
                st.markdown(f"**Objetivo táctico {i+1}.{j+1}**")
                tac_texto = st.text_area(
                    "Enunciado", value=tac["texto"], height=70, key=f"tac_texto_{i}_{j}",
                    label_visibility="collapsed",
                )
                edited_tac_factores, tac_factores_guardar = _editable_factor_table(
                    tac["factores"], key_prefix=f"tac_factores_{i}_{j}"
                )
                peso_tac_total = edited_tac_factores["peso"].sum()
                valor_tac_total = edited_tac_factores["valor"].sum()
                valor_total_tacticos.append(valor_tac_total)
                tacticos_guardar.append({"texto": tac_texto, "factores": tac_factores_guardar})

                cA, cB = st.columns(2)
                cA.metric(f"Suma de pesos (T{i+1}.{j+1})", f"{peso_tac_total:.2f}",
                          help="Debería ser 1.00")
                cB.metric(f"Valor total (T{i+1}.{j+1})", f"{valor_tac_total:.2f}")
                st.markdown(" ")

            # Peso relativo de cada táctico dentro de su OE (según su Valor total)
            suma_valores = sum(valor_total_tacticos) or 1
            pesos_relativos = [v / suma_valores for v in valor_total_tacticos]
            contribuciones = [pr * oe_peso_mision for pr in pesos_relativos]

            st.markdown("**📐 Consolidado: peso relativo y contribución de cada táctico**")
            df_consol = pd.DataFrame({
                "Objetivo táctico": [f"{i+1}.{j+1}" for j in range(len(obj["tacticos"]))],
                "Valor total": valor_total_tacticos,
                "Peso relativo dentro del OE": [f"{p*100:.1f}%" for p in pesos_relativos],
                "Contribución al Objetivo Estratégico": [f"{c:.1f}%" for c in contribuciones],
            })
            st.dataframe(df_consol, use_container_width=True, hide_index=True)

            mejor_tac = int(np.argmax(pesos_relativos))
            st.markdown(
                f"🧭 Dentro de este objetivo estratégico, el **táctico {i+1}.{mejor_tac+1}** es el que "
                f"más pesa ({pesos_relativos[mejor_tac]*100:.1f}% relativo), aportando "
                f"**{contribuciones[mejor_tac]:.1f} puntos porcentuales** al cumplimiento de la misión "
                f"a través de este objetivo estratégico."
            )

            # Guardar todo en session_state
            st.session_state["objetivos"]["objetivos_estrategicos"][i]["eje"] = eje
            st.session_state["objetivos"]["objetivos_estrategicos"][i]["texto"] = texto
            st.session_state["objetivos"]["objetivos_estrategicos"][i]["factores"] = oe_factores_guardar
            st.session_state["objetivos"]["objetivos_estrategicos"][i]["tacticos"] = tacticos_guardar

            resumen_oe_rows.append({
                "Objetivo estratégico": obj["titulo"],
                "% sobre la misión": oe_peso_mision,
                "Táctico más relevante": f"{i+1}.{mejor_tac+1}",
                "Contribución del táctico top": contribuciones[mejor_tac],
            })

    st.divider()

    # ------------------------------------------------------------------
    # 3) Vista consolidada global
    # ------------------------------------------------------------------
    st.subheader("🌐 3. Vista consolidada de los 3 Objetivos Estratégicos")
    df_resumen = pd.DataFrame(resumen_oe_rows)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    fig = px.bar(
        edited_pond, x="porcentaje",
        y=edited_pond["objetivo"].apply(lambda t: t if len(t) <= 55 else t[:52] + "..."),
        orientation="h", title="Contribución de cada Objetivo Estratégico al cumplimiento de la misión",
        color="porcentaje", color_continuous_scale="Blues",
    )
    fig.update_layout(yaxis_title="", xaxis_title="% de cumplimiento de la misión", height=300,
                       coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🧭 Interpretación")
    texto_top = top_obj["objetivo"]
    texto_top_corto = texto_top if len(texto_top) <= 90 else texto_top[:87] + "..."
    st.markdown(
        f"El **Objetivo Estratégico con mayor peso sobre la misión ({top_obj['porcentaje']:.0f}%)** "
        f"es: *\"{texto_top_corto}\"*. Debería recibir prioridad presupuestaria y de seguimiento "
        "gerencial."
    )
    if resumen_oe_rows:
        fila_top = max(resumen_oe_rows, key=lambda r: r["Contribución del táctico top"])
        st.markdown(
            f"En términos operativos, el **objetivo táctico {fila_top['Táctico más relevante']}** "
            f"(dentro de *{fila_top['Objetivo estratégico']}*) es el que más contribuye al avance "
            f"real de la misión, con **{fila_top['Contribución del táctico top']:.1f} puntos** — "
            "es el mejor candidato para asignar recursos y responsables en el corto plazo."
        )
    st.markdown(
        "💡 Cambia cualquier **Peso** o **Importancia** de los factores en las tablas de arriba: la "
        "app recalculará automáticamente el Valor de cada factor, el peso relativo de cada objetivo "
        "táctico dentro de su objetivo estratégico, y su contribución final a la misión."
    )


# ====================================================================
# D. POLÍTICAS
# ====================================================================

def tab_politicas():
    st.header("📜 Políticas")
    data = init_state("politicas", lambda: load_json("politicas"))
    reset_button("politicas", lambda: load_json("politicas"), widget_keys=["editor_politicas"])

    df = pd.DataFrame(data)
    edited = st.data_editor(
        df, key="editor_politicas", num_rows="dynamic", use_container_width=True,
        column_config={
            "titulo": st.column_config.TextColumn("Política", width="medium"),
            "descripcion": st.column_config.TextColumn("Descripción", width="large"),
        },
        height=500,
    )
    st.session_state["politicas"] = edited.to_dict("records")

    st.subheader("🧭 Interpretación")
    st.markdown(
        f"Se han definido **{len(edited)} políticas** que cubren los ámbitos operativo, comercial, "
        "ambiental, de talento humano y de cumplimiento legal. En conjunto, buscan cerrar la brecha "
        "de \"inmadurez administrativa\" identificada en la problemática, convirtiendo cada objetivo "
        "estratégico en reglas de obligado cumplimiento con consecuencias claras ante el incumplimiento."
    )
    kws = {"agua": "ambiental", "certifi": "certificación", "calidad": "calidad",
           "legal": "legal", "seguridad": "seguridad y salud", "mercado": "comercial/mercados",
           "personal": "talento humano", "innovación": "innovación", "ética": "ética"}
    temas = set()
    for row in edited.to_dict("records"):
        texto = (str(row.get("titulo", "")) + " " + str(row.get("descripcion", ""))).lower()
        for k, v in kws.items():
            if k in texto:
                temas.add(v)
    if temas:
        st.markdown(f"- Ámbitos cubiertos detectados automáticamente: **{', '.join(sorted(temas))}**.")


# ====================================================================
# E. VALORES
# ====================================================================

def tab_valores():
    st.header("💎 Valores")
    data = init_state("valores", lambda: load_json("valores"))
    reset_button("valores", lambda: load_json("valores"), widget_keys=["editor_valores"])

    rows = []
    for v in data:
        rows.append({"valor": v["valor"], "comportamientos": "\n".join(f"• {c}" for c in v["comportamientos"])})
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df, key="editor_valores", num_rows="dynamic", use_container_width=True,
        column_config={
            "valor": st.column_config.TextColumn("Valor", width="small"),
            "comportamientos": st.column_config.TextColumn("Comportamientos esperados", width="large"),
        },
        height=380,
    )

    nuevos = []
    for _, row in edited.iterrows():
        comportamientos = [c.lstrip("• ").strip() for c in str(row["comportamientos"]).split("\n") if c.strip()]
        nuevos.append({"valor": row["valor"], "comportamientos": comportamientos})
    st.session_state["valores"] = nuevos

    st.subheader("🧭 Interpretación")
    n_valores = len(nuevos)
    n_comport = sum(len(v["comportamientos"]) for v in nuevos)
    st.markdown(
        f"La organización sostiene su cultura en **{n_valores} valores** ({', '.join(v['valor'] for v in nuevos)}), "
        f"desglosados en **{n_comport} comportamientos observables**. Al estar redactados como "
        "conductas verificables (y no solo como palabras abstractas), estos valores pueden usarse "
        "directamente en evaluaciones de desempeño y en procesos de inducción de nuevo personal."
    )


# ====================================================================
# F. PRINCIPIOS
# ====================================================================

def tab_principios():
    st.header("🧱 Principios")
    data = init_state("principios", lambda: load_json("principios"))
    reset_button("principios", lambda: load_json("principios"), widget_keys=["editor_principios"])

    st.info(
        "Floral Chain Group no cuenta con principios organizacionales formalmente publicados; "
        "esta es una **propuesta** alineada con los objetivos estratégicos, resultado del diagnóstico."
    )

    df = pd.DataFrame(data)
    edited = st.data_editor(
        df, key="editor_principios", num_rows="dynamic", use_container_width=True,
        column_config={
            "nombre": st.column_config.TextColumn("Principio", width="medium"),
            "descripcion": st.column_config.TextColumn("Descripción", width="large"),
        },
        height=320,
    )
    st.session_state["principios"] = edited.to_dict("records")

    st.subheader("🧭 Interpretación")
    st.markdown(
        f"Se proponen **{len(edited)} principios** que orientan la toma de decisiones diaria del "
        "holding. Junto con las políticas y los valores, conforman el marco normativo que la "
        "problemática identificó como ausente — su formalización es un paso necesario para reducir "
        "la exposición legal y reputacional de la organización frente a mercados internacionales."
    )


# ====================================================================
# G. ORGANIGRAMA
# ====================================================================

def tab_organigrama():
    st.header("🗂️ Organigrama")
    st.caption(
        "Estructura organizacional de Floral Chain Group: niveles jerárquicos y áreas de "
        "administración, producción, comercialización e innovación."
    )

    img_path = os.path.join(ASSETS_DIR, "organigrama.png")
    if os.path.exists(img_path):
        st.image(img_path, use_container_width=True, caption="Organigrama general de Floral Chain Group")
    else:
        st.warning("No se encontró la imagen del organigrama en `assets/organigrama.png`.")

    st.subheader("🧭 Interpretación")
    st.markdown(
        "El organigrama permite identificar los niveles jerárquicos y las principales áreas "
        "encargadas de la administración, producción, comercialización e innovación del holding. "
        "Es la base para asignar responsables a cada política, objetivo táctico e indicador "
        "definidos en las pestañas anteriores."
    )

    nuevo = st.file_uploader("Reemplazar imagen del organigrama (opcional)", type=["png", "jpg", "jpeg"])
    if nuevo is not None:
        with open(img_path, "wb") as f:
            f.write(nuevo.getbuffer())
        st.success("Organigrama actualizado. Recarga la pestaña para verlo reflejado.")
        st.rerun()


# ====================================================================
# G-bis. MÓDULO MAPA ESTRATÉGICO (Balanced Scorecard)
# ====================================================================

PERSPECTIVA_COLOR = {
    "Financiera": "#2E9E5B",
    "Cliente": "#3B7DDD",
    "Procesos Internos": "#F0883E",
    "Aprendizaje y crecimiento": "#8E5AC8",
}


def tab_mapa_estrategico_bsc():
    """Sub-pestaña cualitativa (solo lectura): Meta -> Objetivo -> Perspectiva -> Estrategia -> Actividades.
    El filtro de Perspectiva controla qué filas se muestran (no es un campo editable por fila)."""
    data = init_state("mapa_estrategico", lambda: load_json("mapa_estrategico"))
    reset_button("mapa_estrategico", lambda: load_json("mapa_estrategico"),
                  widget_keys=["mapa_filtro_perspectiva"])

    # 🔗 Cumplimiento en vivo desde el CMI Oficial (Estrategias 1-12 + Cuadro de Mando Integral)
    cmi_data = init_state("cmi_oficial", lambda: load_json("cmi_oficial"))
    resultados_estr = calcular_todos_resultados_estrategias()
    cumplimiento_por_objetivo = {}
    for row in cmi_data:
        oid = row.get("objetivo_id")
        if not oid or not row.get("meta"):
            continue
        resultado_pct = resultados_estr.get(row.get("estrategia_id"), 0.0) * 100
        cumplimiento_por_objetivo.setdefault(oid, []).append(resultado_pct / row["meta"] * 100)

    st.info(f"🎯 **Meta general del mapa estratégico:** {data['meta']}")

    conteo_perspectivas = {}
    for obj in data["objetivos"]:
        for fila in obj["filas"]:
            conteo_perspectivas[fila["perspectiva"]] = conteo_perspectivas.get(fila["perspectiva"], 0) + 1

    filtro = st.selectbox(
        "🔍 Filtrar por perspectiva",
        options=["Todas"] + list(PERSPECTIVA_COLOR.keys()),
        key="mapa_filtro_perspectiva",
    )

    with st.container(key=f"mapa_filtro_{filtro}"):
        for oi, obj in enumerate(data["objetivos"]):
            filas_visibles = [
                fila for fila in obj["filas"] if filtro == "Todas" or fila["perspectiva"] == filtro
            ]
            if not filas_visibles:
                continue

            # 🔗 El texto vigente viene siempre de la pestaña 🏁 Objetivos (fuente única)
            texto_obj = objetivo_texto(obj.get("objetivo_id"), fallback=obj["objetivo"])
            with st.expander(f"**Objetivo estratégico {oi+1}** — {texto_obj[:90]}...", expanded=(oi == 0)):
                st.markdown(f"**Objetivo estratégico:** {texto_obj}")

                valores_cmi = cumplimiento_por_objetivo.get(obj.get("objetivo_id"))
                if valores_cmi:
                    cumpl_prom = sum(valores_cmi) / len(valores_cmi)
                    sem = calcular_semaforo(cumpl_prom)
                    info_sem = SEMAFORO_INFO[sem]
                    st.caption(
                        f"🔗 Cumplimiento CMI de este objetivo (en vivo, {len(valores_cmi)} indicador"
                        f"{'es' if len(valores_cmi) != 1 else ''}): **{cumpl_prom:.1f}%** "
                        f"{info_sem['icono']} {sem}"
                    )

                for fila in filas_visibles:
                    st.markdown("---")
                    color = PERSPECTIVA_COLOR.get(fila["perspectiva"], "#999999")
                    st.markdown(
                        f"<span style='background-color:{color};color:white;padding:2px 10px;"
                        f"border-radius:12px;font-size:0.85em;'>{fila['perspectiva']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**Estrategia:** {fila['estrategia']}")
                    st.markdown("**Actividades:**")
                    for act in fila["actividades"]:
                        st.markdown(f"- {act}")
                    cA, cB = st.columns(2)
                    cA.markdown(f"**Responsable:** {fila['responsable']}")
                    cB.markdown(f"**KPI:** {fila['kpi']}")

    st.subheader("🧭 Interpretación")
    if conteo_perspectivas:
        df_persp = pd.DataFrame({
            "Perspectiva": list(conteo_perspectivas.keys()),
            "N° de estrategias": list(conteo_perspectivas.values()),
        }).sort_values("N° de estrategias", ascending=False)
        fig = px.bar(df_persp, x="Perspectiva", y="N° de estrategias", color="Perspectiva",
                     color_discrete_map=PERSPECTIVA_COLOR, title="Estrategias por perspectiva del BSC")
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

        top_persp = df_persp.iloc[0]
        st.markdown(
            f"La perspectiva **{top_persp['Perspectiva']}** concentra la mayor parte del mapa "
            f"estratégico ({int(top_persp['N° de estrategias'])} de {sum(conteo_perspectivas.values())} "
            "estrategias), lo que confirma que el esfuerzo actual del holding está puesto en fortalecer "
            "sus capacidades internas (procesos, cultura y aprendizaje) más que en resultados financieros "
            "directos — coherente con la problemática de inmadurez administrativa identificada."
        )


def tab_mapa_estrategico():
    st.header("🗺️ Mapa Estratégico")
    st.caption(
        "Balanced Scorecard de Floral Chain Group: conecta la meta general con cada objetivo "
        "estratégico, las 4 perspectivas (Financiera, Cliente, Procesos Internos, Aprendizaje y "
        "Crecimiento), las estrategias/actividades y sus KPIs de cumplimiento. Vista cualitativa, "
        "de solo lectura (fiel al documento) y filtrable por perspectiva. 🔗 Cada objetivo muestra "
        "su cumplimiento CMI en vivo (sección **CMI**) — para editar esos valores, ve allá."
    )
    tab_mapa_estrategico_bsc()


# ====================================================================
# H. MÓDULO PLANES (Financiero, Marketing, Operaciones, Mejoras,
#    Tecnológico, Compras, Control)
# ====================================================================

PLAN_ICONS = {
    "PLAN FINANCIERO": "💰",
    "PLAN DE MARKETING": "📣",
    "PLAN DE OPERACIONES": "⚙️",
    "PLAN DE MEJORAS": "🛠️",
    "PLAN TECNOLOGICO O DE SISTEMAS": "💻",
    "PLAN DE COMPRAS": "🛒",
    "PLAN DE CONTROL": "🧮",
}


def _plan_grand_total(plan):
    return sum(a["costo"] for e in plan["estrategias"] for a in e["actividades"])


def _render_un_plan(plan, plan_idx):
    """Renderiza un plan individual: cabecera ligada a Misión/Visión, bloques de
    estrategia editables y el TOTAL recalculado automáticamente."""
    mv = st.session_state.get("mision_vision") or load_json("mision_vision")

    with st.container(border=True):
        st.markdown(f"**Misión (ligada a la pestaña Misión y Visión):** {mv['mision_propuesta']}")
        c1, c2 = st.columns(2)
        c1.markdown(f"**Periodo:** {plan['periodo']}")
        c2.markdown(f"**Moneda:** {plan['moneda']}")

    total_plan = 0.0
    for ei, estr in enumerate(plan["estrategias"]):
        st.markdown(f"#### 🎯 {estr['tipo_estrategia']}")
        st.caption(estr["estrategia"])

        df = pd.DataFrame(estr["actividades"])
        edited = st.data_editor(
            df,
            key=f"plan_{plan_idx}_estr_{ei}",
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "actividad": st.column_config.TextColumn("Actividad", width="large"),
                "responsable": st.column_config.TextColumn("Responsable", width="medium"),
                "tiempo": st.column_config.TextColumn("Tiempo", width="small"),
                "costo": NUM_COL("Costo aprox. (USD)", min_value=0.0, step=50.0, format="%.2f"),
                "tipo_cuenta": st.column_config.TextColumn("Tipo de cuenta", width="medium"),
            },
        )
        st.session_state["planes"]["planes"][plan_idx]["estrategias"][ei]["actividades"] = (
            edited.to_dict("records")
        )
        subtotal = edited["costo"].sum()
        total_plan += subtotal
        st.caption(f"Subtotal de este bloque: **${subtotal:,.2f}**")
        st.markdown("---")

    st.subheader(f"💵 TOTAL {plan['nombre']}: ${total_plan:,.2f}")
    return total_plan


def tab_planes():
    st.header("📁 Planes de Acción")
    st.caption(
        "Cada plan traduce una estrategia FODA (FO/FA/DO/DA — visibles en la pestaña 🔢 FODA "
        "Numérico) en actividades concretas con responsable, tiempo y **costo editable**. Cambia "
        "cualquier costo y el TOTAL del plan y el resumen consolidado se recalculan al instante."
    )

    data = init_state("planes", lambda: load_json("planes"))
    reset_button("planes", lambda: load_json("planes"), widget_keys=["plan_"])

    nombres = [p["nombre"] for p in data["planes"]]
    tab_labels = [f"{PLAN_ICONS.get(n, '📄')} {n.title()}" for n in nombres]
    sub_tabs = st.tabs(tab_labels + ["📊 Resumen consolidado"])

    totales = {}
    for idx, plan in enumerate(data["planes"]):
        with sub_tabs[idx]:
            totales[plan["nombre"]] = _render_un_plan(plan, idx)

    # ------------------------------------------------------------------
    # Resumen consolidado — se recalcula con los valores editados arriba
    # ------------------------------------------------------------------
    with sub_tabs[-1]:
        st.subheader("📊 Resumen consolidado de los 7 planes")
        df_resumen = pd.DataFrame({
            "Plan": list(totales.keys()),
            "Costo total (USD)": list(totales.values()),
        }).sort_values("Costo total (USD)", ascending=False)

        gran_total = df_resumen["Costo total (USD)"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Presupuesto total de los 7 planes", f"${gran_total:,.2f}")
        c2.metric("Plan de mayor costo", df_resumen.iloc[0]["Plan"])
        c3.metric("Costo del plan más caro", f"${df_resumen.iloc[0]['Costo total (USD)']:,.2f}")

        st.dataframe(
            df_resumen.style.format({"Costo total (USD)": "${:,.2f}"}),
            use_container_width=True, hide_index=True,
        )

        fig = px.bar(
            df_resumen, x="Costo total (USD)", y="Plan", orientation="h",
            color="Plan", title="Costo total por plan de acción",
        )
        fig.update_layout(showlegend=False, height=380, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.pie(
            df_resumen, names="Plan", values="Costo total (USD)",
            title="Distribución del presupuesto entre los 7 planes",
        )
        fig2.update_layout(height=420)
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("🧭 Interpretación")
        top = df_resumen.iloc[0]
        bottom = df_resumen.iloc[-1]
        pct_top = top["Costo total (USD)"] / gran_total * 100 if gran_total else 0
        st.markdown(
            f"El **{top['Plan'].title()}** concentra el mayor presupuesto "
            f"(**${top['Costo total (USD)']:,.2f}**, el {pct_top:.0f}% del total), lo que refleja "
            "dónde la organización está poniendo más recursos para ejecutar su estrategia."
        )
        st.markdown(
            f"El **{bottom['Plan'].title()}** es el de menor costo "
            f"(**${bottom['Costo total (USD)']:,.2f}**) — conviene verificar que su alcance sea "
            "suficiente frente al objetivo estratégico que busca atender."
        )
        st.info(
            "💡 Todo está conectado: si editas un costo en cualquier plan, este resumen, los "
            "gráficos y el TOTAL de ese plan se actualizan automáticamente. La Misión mostrada en "
            "cada plan también proviene directamente de la pestaña 🎯 Misión y Visión — si la "
            "cambias ahí, se refleja aquí."
        )


# ====================================================================
# 1. MATRIZ HOLMES / MICMAC
# ====================================================================

def tab_holmes():
    st.header("🔗 Matriz Holmes (Análisis MICMAC de Motricidad y Dependencia)")
    st.caption(
        "Cada celda indica el nivel de influencia (0 = nula, 1 = débil, 2 = media, "
        "3 = fuerte) de la variable de la FILA sobre la variable de la COLUMNA. "
        "La diagonal se excluye siempre del cálculo."
    )

    data = init_state("holmes", lambda: load_json("holmes"))
    reset_button("holmes", lambda: load_json("holmes"),
                  widget_keys=["editor_holmes_", "holmes_nombres_"])

    bloque = st.radio(
        "Selecciona el bloque de variables:",
        options=["F - Fortalezas", "D - Debilidades", "A - Amenazas", "O - Oportunidades"],
        horizontal=True,
    )
    clave = bloque[0]
    with st.container(key=f"holmes_bloque_{clave}"):
        block = data[clave]
        n = len(block["matrix"])
        codes = [f"{clave}{i+1}" for i in range(n)]

        compartido = clave in ("F", "D")
        if compartido:
            # F y D son los mismos factores que EFI y FODA Numérico -> vienen del
            # registro maestro, y se pueden renombrar aquí (se refleja en ambos).
            labels = [factor_nombre(clave, c) for c in codes]
            with st.expander("✏️ Editar nombres de las variables (compartidos con EFI y FODA Numérico)"):
                df_nombres = pd.DataFrame({"Código": codes, "Nombre": labels})
                edited_nombres = st.data_editor(
                    df_nombres, key=f"holmes_nombres_{clave}", hide_index=True,
                    use_container_width=True,
                    column_config={"Código": st.column_config.TextColumn("Código", disabled=True)},
                )
                for c, nuevo in zip(codes, edited_nombres["Nombre"].tolist()):
                    set_factor_nombre(clave, c, nuevo)
                labels = edited_nombres["Nombre"].tolist()
        else:
            labels = block["labels"]

        matrix_canonica_actual = np.array(
            [[0.0 if v is None else v for v in row] for row in block["matrix"]]
        )
        vals_actual = matrix_canonica_actual.copy()
        np.fill_diagonal(vals_actual, 0.0)
        motricidad_actual = vals_actual.sum(axis=1)
        # 🔢 Orden de prioridad: de mayor a menor motricidad (la más alta va primera)
        orden_idx = list(np.argsort(-motricidad_actual))

        codes_ord = [codes[i] for i in orden_idx]
        labels_ord = [labels[i] for i in orden_idx]
        matrix_ord = matrix_canonica_actual[np.ix_(orden_idx, orden_idx)]

        df = pd.DataFrame(matrix_ord, index=labels_ord, columns=codes_ord)
        # Guardamos máscara diagonal para excluirla siempre del cálculo
        edited = st.data_editor(
            df,
            key=f"editor_holmes_{clave}",
            use_container_width=True,
            column_config={c: NUM_COL(c, min_value=0, max_value=3, step=1) for c in codes_ord},
        )

        # Persistir la matriz editada en el orden CANÓNICO (F1..F11/D1..D11), aunque
        # se muestre y edite reordenada por prioridad (antes se perdía al cambiar de
        # bloque o pestaña)
        edited_vals = edited.to_numpy(dtype=float)
        n_vars = len(orden_idx)
        matriz_canonica_nueva = [[0.0] * n_vars for _ in range(n_vars)]
        for a, real_i in enumerate(orden_idx):
            for b, real_j in enumerate(orden_idx):
                matriz_canonica_nueva[real_i][real_j] = edited_vals[a][b]
        for i in range(n_vars):
            matriz_canonica_nueva[i][i] = None  # la diagonal siempre se guarda como null
        st.session_state["holmes"][clave]["matrix"] = matriz_canonica_nueva
        if not compartido:
            st.session_state["holmes"][clave]["labels"] = labels

        vals = np.array([[0.0 if v is None else v for v in row] for row in matriz_canonica_nueva])
        np.fill_diagonal(vals, 0.0)  # la diagonal nunca cuenta, se edite o no

        motricidad = vals.sum(axis=1)   # suma por fila -> cuánto influye
        dependencia = vals.sum(axis=0)  # suma por columna -> cuánto es influida

        suma_motricidad = motricidad.sum()
        ponderacion_pct = (motricidad / suma_motricidad * 100) if suma_motricidad > 0 else np.zeros_like(motricidad)

        resumen = pd.DataFrame(
            {
                "Variable": labels,
                "Código": codes,
                "Motricidad (influye)": motricidad.astype(int),
                "Dependencia (es influida)": dependencia.astype(int),
                "Ponderación (%)": np.round(ponderacion_pct, 1),
            }
        ).sort_values("Motricidad (influye)", ascending=False)

        promedio_row = pd.DataFrame([{
            "Variable": "PROMEDIO", "Código": "—",
            "Motricidad (influye)": round(motricidad.mean(), 2),
            "Dependencia (es influida)": round(dependencia.mean(), 2),
            "Ponderación (%)": round(100 / len(motricidad), 1) if len(motricidad) else 0,
        }])
        resumen_con_promedio = pd.concat([resumen, promedio_row], ignore_index=True)

        col1, col2 = st.columns([1.1, 1])
        with col1:
            st.subheader("Resumen de motricidad / dependencia")
            st.caption(
                "Ordenado de mayor a menor prioridad (Ponderación %). La fila PROMEDIO marca el "
                "umbral usado para clasificar los cuadrantes del plano MICMAC."
            )
            st.dataframe(resumen_con_promedio, use_container_width=True, hide_index=True)

        with col2:
            mean_m = motricidad.mean() if motricidad.mean() > 0 else 1
            mean_d = dependencia.mean() if dependencia.mean() > 0 else 1

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=dependencia,
                    y=motricidad,
                    mode="markers+text",
                    text=codes,
                    textposition="top center",
                    marker=dict(size=12, color="#3B7DDD"),
                )
            )
            fig.add_vline(x=mean_d, line_dash="dash", line_color="gray")
            fig.add_hline(y=mean_m, line_dash="dash", line_color="gray")
            fig.update_layout(
                title="Plano MICMAC: Motricidad vs. Dependencia",
                xaxis_title="Dependencia",
                yaxis_title="Motricidad",
                height=430,
                margin=dict(t=50, l=10, r=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Clasificación por cuadrante
        mean_m = motricidad.mean() if motricidad.mean() > 0 else 1
        mean_d = dependencia.mean() if dependencia.mean() > 0 else 1
        cuadrantes = {"Clave/Motrices": [], "Enlace": [], "Dependientes": [], "Autónomas": []}
        for i, code in enumerate(codes):
            alta_m = motricidad[i] >= mean_m
            alta_d = dependencia[i] >= mean_d
            if alta_m and not alta_d:
                cuadrantes["Clave/Motrices"].append((code, labels[i]))
            elif alta_m and alta_d:
                cuadrantes["Enlace"].append((code, labels[i]))
            elif not alta_m and alta_d:
                cuadrantes["Dependientes"].append((code, labels[i]))
            else:
                cuadrantes["Autónomas"].append((code, labels[i]))

        st.subheader("🧭 Interpretación estratégica")
        nombre_bloque = {
            "F": "fortalezas", "D": "debilidades", "A": "amenazas", "O": "oportunidades",
        }[clave]

        textos = {
            "Clave/Motrices": (
                f"**Variables clave / motrices** (alta motricidad, baja dependencia): son las "
                f"{nombre_bloque} que **mueven al sistema**. Actuar sobre ellas genera el mayor "
                f"efecto de arrastre sobre el resto — deben priorizarse en la formulación de estrategias."
            ),
            "Enlace": (
                "**Variables de enlace** (alta motricidad y alta dependencia): son inestables por "
                "naturaleza — cualquier acción sobre ellas repercute en el sistema, pero a la vez "
                "son sensibles a lo que ocurre en las demás. Requieren monitoreo constante."
            ),
            "Dependientes": (
                f"**Variables dependientes** (baja motricidad, alta dependencia): son en gran medida "
                f"el **resultado** de lo que pase con las variables motrices. Sirven como indicadores "
                f"de seguimiento del avance estratégico, no como palancas de acción directa."
            ),
            "Autónomas": (
                "**Variables autónomas** (baja motricidad, baja dependencia): tienen poca relación "
                "con el resto del sistema. Su prioridad estratégica es baja salvo que cambien de "
                "posición al reponderar los valores."
            ),
        }

        for cuad, items in cuadrantes.items():
            if items:
                nombres = ", ".join(f"**{c}** ({n})" for c, n in items)
                st.markdown(f"- {textos[cuad]}\n  \n  📌 Ubicadas aquí: {nombres}")

        if len(cuadrantes["Clave/Motrices"]) == 0:
            st.info(
                "Con los valores actuales ninguna variable domina claramente el sistema: "
                "la influencia está repartida de forma homogénea entre todas las "
                f"{nombre_bloque}."
            )


# ====================================================================
# 2. EFI
# ====================================================================

def calc_efi_efe(rows_pos, rows_neg, label_pos, label_neg):
    def build(rows, tipo):
        df = pd.DataFrame(rows)
        df.insert(1, "tipo", tipo)
        return df

    df = pd.concat(
        [build(rows_pos, label_pos), build(rows_neg, label_neg)], ignore_index=True
    )
    df["peso_ponderado"] = df["peso"] * df["calificacion"]
    return df


def tab_efi():
    st.header("🏭 EFI — Evaluación de Factores Internos")
    st.caption(
        "Edita el **peso** (relevancia relativa, entre 0 y 1) y la **calificación** "
        "(1 = debilidad mayor, 2 = debilidad menor, 3 = fortaleza menor, 4 = fortaleza mayor)."
    )

    data = init_state("efi", lambda: load_json("efi"))
    reset_button("efi", lambda: load_json("efi"), widget_keys=["editor_efi_f", "editor_efi_d"])

    st.caption(
        "🔗 Los nombres de los factores (F1-F11 / D1-D11) están **compartidos con la Matriz "
        "Holmes y el FODA Numérico** — renombrarlos aquí (o allá) se refleja en las tres."
    )

    def _rows_con_nombre(rows, tipo):
        out = []
        for r in rows:
            codigo = r.get("codigo", "")
            nombre = factor_nombre(tipo, codigo) if codigo else r.get("factor", "")
            out.append({"codigo": codigo, "factor": nombre, "peso": r["peso"], "calificacion": r["calificacion"]})
        return out

    def _guardar_grupo(edited_df, tipo):
        registros = []
        for _, row in edited_df.iterrows():
            codigo = row.get("codigo") or ""
            if codigo:
                set_factor_nombre(tipo, codigo, row["factor"])
            registros.append({"codigo": codigo, "peso": row["peso"], "calificacion": row["calificacion"]})
        return registros

    st.subheader("Fortalezas")
    df_f = pd.DataFrame(_rows_con_nombre(data["fortalezas"], "F"))
    edited_f = st.data_editor(
        df_f,
        key="editor_efi_f",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "codigo": st.column_config.TextColumn("Código", width="small", disabled=True),
            "factor": st.column_config.TextColumn("Fortaleza", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "calificacion": st.column_config.SelectboxColumn(
                "Calificación", options=[1, 2, 3, 4]
            ),
        },
    )

    st.subheader("Debilidades")
    df_d = pd.DataFrame(_rows_con_nombre(data["debilidades"], "D"))
    edited_d = st.data_editor(
        df_d,
        key="editor_efi_d",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "codigo": st.column_config.TextColumn("Código", width="small", disabled=True),
            "factor": st.column_config.TextColumn("Debilidad", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "calificacion": st.column_config.SelectboxColumn(
                "Calificación", options=[1, 2, 3, 4]
            ),
        },
    )

    # Persistir peso/calificación (antes se perdían) y propagar renombres al registro maestro
    st.session_state["efi"]["fortalezas"] = _guardar_grupo(edited_f, "F")
    st.session_state["efi"]["debilidades"] = _guardar_grupo(edited_d, "D")

    edited_f = edited_f.assign(peso_ponderado=edited_f["peso"] * edited_f["calificacion"])
    edited_d = edited_d.assign(peso_ponderado=edited_d["peso"] * edited_d["calificacion"])

    total_peso = edited_f["peso"].sum() + edited_d["peso"].sum()
    total_ponderado = edited_f["peso_ponderado"].sum() + edited_d["peso_ponderado"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Suma de pesos", f"{total_peso:.2f}", help="Debe ser igual a 1.00")
    c2.metric("Total ponderado EFI", f"{total_ponderado:.2f}")
    c3.metric(
        "Peso Fortalezas vs Debilidades",
        f"{edited_f['peso'].sum():.2f} / {edited_d['peso'].sum():.2f}",
    )

    if abs(total_peso - 1.0) > 0.01:
        st.warning(
            f"⚠️ La suma de los pesos es **{total_peso:.2f}**, debería ser 1.00. "
            "Ajusta los pesos para que la evaluación sea válida."
        )

    st.subheader("🧭 Interpretación")
    nivel_efi = clasificar_bmm(total_ponderado, umbral_bueno=3.0, umbral_medio=2.0)
    st.metric("Evaluación general EFI", nivel_efi)
    if total_ponderado >= 2.5:
        fuerza = (
            f"El total ponderado es **{total_ponderado:.2f} (≥ 2.5)**, lo que indica que la "
            "organización tiene una **posición interna sólida**: sus fortalezas superan a sus "
            "debilidades en el peso estratégico."
        )
    else:
        fuerza = (
            f"El total ponderado es **{total_ponderado:.2f} (< 2.5)**, lo que indica una "
            "**posición interna débil**: las debilidades pesan más que las fortalezas y deben "
            "atenderse con prioridad."
        )
    st.markdown(fuerza)

    top_f = edited_f.sort_values("peso_ponderado", ascending=False).iloc[0]
    top_d = edited_d.sort_values("peso_ponderado", ascending=False).iloc[0]
    st.markdown(
        f"- La **fortaleza de mayor peso estratégico** es *{top_f['factor']}* "
        f"(ponderado {top_f['peso_ponderado']:.2f}); conviene capitalizarla en las estrategias."
    )
    st.markdown(
        f"- La **debilidad más crítica** es *{top_d['factor']}* "
        f"(ponderado {top_d['peso_ponderado']:.2f}); debe ser el foco de los planes de mejora interna."
    )

    fig = px.bar(
        pd.concat([edited_f.assign(tipo="Fortaleza"), edited_d.assign(tipo="Debilidad")]),
        x="peso_ponderado", y="factor", color="tipo", orientation="h",
        color_discrete_map={"Fortaleza": "#2E9E5B", "Debilidad": "#D9534F"},
        title="Peso ponderado por factor interno",
    )
    fig.update_layout(yaxis_title="", xaxis_title="Peso ponderado", height=500)
    st.plotly_chart(fig, use_container_width=True)


# ====================================================================
# 3. EFE
# ====================================================================

def tab_efe():
    st.header("🌍 EFE — Evaluación de Factores Externos")
    st.caption(
        "Edita el **peso** y la **calificación** (1 = respuesta mala, 2 = respuesta media, "
        "3 = respuesta superior a la media, 4 = respuesta superior)."
    )

    data = init_state("efe", lambda: load_json("efe"))
    reset_button("efe", lambda: load_json("efe"), widget_keys=["editor_efe_o", "editor_efe_a"])

    cols_orden = ["codigo", "factor", "peso", "calificacion"]

    st.subheader("Oportunidades")
    df_o = pd.DataFrame(data["oportunidades"])[cols_orden]
    edited_o = st.data_editor(
        df_o, key="editor_efe_o", num_rows="dynamic", use_container_width=True,
        column_config={
            "codigo": st.column_config.TextColumn("Código", width="small", disabled=True),
            "factor": st.column_config.TextColumn("Oportunidad", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "calificacion": st.column_config.SelectboxColumn("Calificación", options=[1, 2, 3, 4]),
        },
    )

    st.subheader("Amenazas")
    df_a = pd.DataFrame(data["amenazas"])[cols_orden]
    edited_a = st.data_editor(
        df_a, key="editor_efe_a", num_rows="dynamic", use_container_width=True,
        column_config={
            "codigo": st.column_config.TextColumn("Código", width="small", disabled=True),
            "factor": st.column_config.TextColumn("Amenaza", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "calificacion": st.column_config.SelectboxColumn("Calificación", options=[1, 2, 3, 4]),
        },
    )

    # Persistir los cambios (antes se perdían) — el código se conserva porque
    # la pestaña Cadena de Valor lo usa para recalcular sus etapas vinculadas.
    st.session_state["efe"]["oportunidades"] = edited_o.to_dict("records")
    st.session_state["efe"]["amenazas"] = edited_a.to_dict("records")

    edited_o = edited_o.assign(peso_ponderado=edited_o["peso"] * edited_o["calificacion"])
    edited_a = edited_a.assign(peso_ponderado=edited_a["peso"] * edited_a["calificacion"])

    total_peso = edited_o["peso"].sum() + edited_a["peso"].sum()
    total_ponderado = edited_o["peso_ponderado"].sum() + edited_a["peso_ponderado"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Suma de pesos", f"{total_peso:.2f}", help="Debe ser igual a 1.00")
    c2.metric("Total ponderado EFE", f"{total_ponderado:.2f}")
    c3.metric(
        "Peso Oportunidades vs Amenazas",
        f"{edited_o['peso'].sum():.2f} / {edited_a['peso'].sum():.2f}",
    )

    if abs(total_peso - 1.0) > 0.01:
        st.warning(f"⚠️ La suma de pesos es **{total_peso:.2f}**, debería ser 1.00.")

    st.subheader("🧭 Interpretación")
    nivel_efe = clasificar_bmm(total_ponderado, umbral_bueno=3.0, umbral_medio=2.0)
    st.metric("Evaluación general EFE", nivel_efe)
    if total_ponderado >= 2.5:
        st.markdown(
            f"El total ponderado es **{total_ponderado:.2f} (≥ 2.5)**: la organización "
            "**responde bien al entorno**, aprovechando oportunidades y neutralizando amenazas "
            "de forma eficaz."
        )
    else:
        st.markdown(
            f"El total ponderado es **{total_ponderado:.2f} (< 2.5)**: la organización "
            "**no está aprovechando** adecuadamente las oportunidades ni mitigando las amenazas "
            "del entorno; se requieren estrategias externas más agresivas."
        )

    top_o = edited_o.sort_values("peso_ponderado", ascending=False).iloc[0]
    top_a = edited_a.sort_values("peso_ponderado", ascending=False).iloc[0]
    st.markdown(f"- **Oportunidad más relevante:** {top_o['factor']} (ponderado {top_o['peso_ponderado']:.2f}).")
    st.markdown(f"- **Amenaza más crítica:** {top_a['factor']} (ponderado {top_a['peso_ponderado']:.2f}).")

    fig = px.bar(
        pd.concat([edited_o.assign(tipo="Oportunidad"), edited_a.assign(tipo="Amenaza")]),
        x="peso_ponderado", y="factor", color="tipo", orientation="h",
        color_discrete_map={"Oportunidad": "#3B7DDD", "Amenaza": "#D9534F"},
        title="Peso ponderado por factor externo",
    )
    fig.update_layout(yaxis_title="", xaxis_title="Peso ponderado", height=650)
    st.plotly_chart(fig, use_container_width=True)


# ====================================================================
# 4. CADENA DE VALOR
# ====================================================================

def tab_cadena_valor():
    st.header("⛓️ Cadena de Valor")
    st.caption(
        "Describe cada etapa, su peso dentro de la cadena y el cuello de botella. "
        "🔗 **La Calificación y el Valor Ponderado no se editan aquí**: cada etapa está vinculada a "
        "un factor de EFI o EFE, y se recalculan solos en cuanto cambias la calificación de ese "
        "factor en su pestaña de origen."
    )

    data = init_state("cadena", lambda: load_json("cadena_valor"))
    reset_button("cadena", lambda: load_json("cadena_valor"), widget_keys=["editor_cadena"])
    # Asegura que EFI/EFE existan en session_state aunque el usuario no haya visitado esas pestañas
    init_state("efi", lambda: load_json("efi"))
    init_state("efe", lambda: load_json("efe"))

    filas = []
    for stage in data:
        rel = stage.get("factor_relacionado")
        calif = factor_calificacion(rel["fuente"], rel["codigo"]) if rel else None
        calif = calif if calif is not None else 0.0
        resultado = clasificar_bmm(calif, umbral_bueno=3.0, umbral_medio=2.0).replace(
            "Bueno", "Éxito"
        ).replace("Malo", "Pérdida / cuello crítico")
        filas.append({
            "etapa": stage["etapa"],
            "actividad": stage["actividad"],
            "peso": stage["peso"],
            "vinculo": f"{rel['fuente']} {rel['codigo']}" if rel else "—",
            "factor_vinculado": factor_display_nombre(rel["fuente"], rel["codigo"]) if rel else "",
            "calificacion": calif,
            "resultado": resultado,
            "cuello_botella": stage["cuello_botella"],
        })
    df = pd.DataFrame(filas)

    edited = st.data_editor(
        df, key="editor_cadena", num_rows="fixed", use_container_width=True,
        column_config={
            "etapa": st.column_config.TextColumn("Etapa del proceso", width="medium", disabled=True),
            "actividad": st.column_config.TextColumn("Actividad y valor generado", width="large"),
            "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
            "vinculo": st.column_config.TextColumn("Vínculo", width="small", disabled=True),
            "factor_vinculado": st.column_config.TextColumn("Factor vinculado (EFI/EFE)", width="medium", disabled=True),
            "calificacion": NUM_COL("Calificación (derivada)", format="%.1f", disabled=True),
            "resultado": st.column_config.TextColumn("Resultado", width="medium", disabled=True),
            "cuello_botella": st.column_config.TextColumn("Cuello de botella", width="large"),
        },
        height=460,
    )
    edited["valor_ponderado"] = edited["peso"] * edited["calificacion"]

    # Persistir peso / actividad / cuello de botella (la calificación es siempre derivada)
    for i, row in edited.iterrows():
        st.session_state["cadena"][i]["peso"] = float(row["peso"])
        st.session_state["cadena"][i]["actividad"] = row["actividad"]
        st.session_state["cadena"][i]["cuello_botella"] = row["cuello_botella"]

    total_peso = edited["peso"].sum()
    total_valor = edited["valor_ponderado"].sum()
    c1, c2 = st.columns(2)
    c1.metric("Suma de pesos", f"{total_peso:.2f}", help="Debe ser 1.00")
    c2.metric("Valor ponderado total", f"{total_valor:.2f}")
    if abs(total_peso - 1.0) > 0.01:
        st.warning(f"⚠️ La suma de pesos es **{total_peso:.2f}**, debería ser 1.00.")

    def es_si(texto):
        return isinstance(texto, str) and texto.strip().lower().startswith("si")

    n_total = len(edited)
    n_cuellos = edited["cuello_botella"].apply(es_si).sum()
    pct = (n_cuellos / n_total * 100) if n_total else 0

    c1, c2 = st.columns(2)
    c1.metric("Etapas con cuello de botella", f"{n_cuellos} / {n_total}")
    c2.metric("% de etapas críticas", f"{pct:.0f}%")

    st.subheader("🧭 Interpretación")
    for resultado in ["Éxito", "Medio", "Pérdida / cuello crítico"]:
        etapas_resultado = edited.loc[
            edited["resultado"].str.contains(resultado, na=False), "etapa"
        ].tolist()
        if etapas_resultado:
            st.markdown(f"- **{resultado}**: " + ", ".join(etapas_resultado) + ".")

    peor = edited.sort_values("valor_ponderado").iloc[0]
    st.markdown(
        f"- La etapa con **menor valor ponderado** es **{peor['etapa']}** "
        f"({peor['valor_ponderado']:.2f}), vinculada a *{peor['factor_vinculado']}* "
        f"({peor['vinculo']}) — mejorar la calificación de ese factor en EFI/EFE elevaría "
        "directamente el desempeño de esta etapa."
    )
    etapas_criticas = edited.loc[edited["cuello_botella"].apply(es_si), "etapa"].tolist()
    if pct >= 50:
        st.markdown(
            f"**Más de la mitad de la cadena de valor ({pct:.0f}%) presenta cuellos de botella.** "
            "Esto sugiere una cadena vulnerable donde varios eslabones limitan simultáneamente la "
            "capacidad de respuesta; se recomienda priorizar inversión en las etapas: "
            + ", ".join(etapas_criticas) + "."
        )
    elif n_cuellos > 0:
        st.markdown(
            f"Se identificaron **{n_cuellos} etapa(s) crítica(s)** ({', '.join(etapas_criticas)}). "
            "El resto de la cadena opera sin restricciones relevantes, por lo que los esfuerzos de "
            "mejora pueden concentrarse puntualmente en esos eslabones."
        )
    else:
        st.markdown(
            "No hay etapas marcadas con cuello de botella: la cadena de valor, según los datos "
            "actuales, no presenta restricciones críticas identificadas."
        )


# ====================================================================
# 5. MATRIZ DE PERFIL COMPETITIVO (MPC)
# ====================================================================

def tab_mpc():
    st.header("🏆 Matriz de Perfil Competitivo (MPC)")
    st.caption(
        "Edita el **peso** de cada factor crítico de éxito y la **calificación** (1 a 4) de "
        "cada competidor. Puedes renombrar los competidores."
    )

    data = init_state("mpc", lambda: load_json("mpc"))
    reset_button("mpc", lambda: load_json("mpc"), widget_keys=["editor_mpc", "mpc_name_"])

    companies = st.session_state["mpc"]["companies"]
    new_names = []
    cols = st.columns(len(companies))
    for i, c in enumerate(companies):
        new_names.append(cols[i].text_input(f"Nombre competidor {i+1}", value=c, key=f"mpc_name_{i}"))
    st.session_state["mpc"]["companies"] = new_names
    companies = new_names

    rows = []
    for f in data["factores"]:
        row = {"factor": f["factor"], "peso": f["peso"]}
        for i, c in enumerate(companies):
            row[c] = f["ratings"][i]
        rows.append(row)
    df = pd.DataFrame(rows)

    col_config = {
        "factor": st.column_config.TextColumn("Factor Crítico de Éxito", width="large"),
        "peso": NUM_COL("Peso", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
    }
    for c in companies:
        col_config[c] = st.column_config.SelectboxColumn(c, options=[1, 2, 3, 4])

    edited = st.data_editor(
        df, key="editor_mpc", num_rows="dynamic", use_container_width=True, column_config=col_config,
    )

    # Persistir factores/pesos/calificaciones editados (antes se perdían)
    st.session_state["mpc"]["factores"] = [
        {"factor": row["factor"], "peso": row["peso"], "ratings": [row[c] for c in companies]}
        for _, row in edited.iterrows()
    ]

    total_peso = edited["peso"].sum()
    totals = {}
    ponderados = edited[["factor", "peso"]].copy()
    for c in companies:
        ponderados[f"pond_{c}"] = edited["peso"] * edited[c]
        totals[c] = ponderados[f"pond_{c}"].sum()

    st.metric("Suma de pesos", f"{total_peso:.2f}", help="Debe ser igual a 1.00")
    if abs(total_peso - 1.0) > 0.01:
        st.warning(f"⚠️ La suma de pesos es **{total_peso:.2f}**, debería ser 1.00.")

    st.subheader("Puntaje ponderado total por competidor")
    df_tot = pd.DataFrame({"Competidor": list(totals.keys()), "Puntaje total": list(totals.values())})
    df_tot["Evaluación"] = df_tot["Puntaje total"].apply(
        lambda v: clasificar_bmm(v, umbral_bueno=3.0, umbral_medio=2.0)
    )
    df_tot = df_tot.sort_values("Puntaje total", ascending=False)
    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.dataframe(df_tot, use_container_width=True, hide_index=True)
    with c2:
        fig = px.bar(df_tot, x="Competidor", y="Puntaje total", color="Competidor",
                     title="Comparación de competitividad")
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🧭 Interpretación")
    lider = df_tot.iloc[0]
    ultimo = df_tot.iloc[-1]
    st.markdown(
        f"**{lider['Competidor']}** lidera el perfil competitivo con un puntaje de "
        f"**{lider['Puntaje total']:.2f}**, mientras que **{ultimo['Competidor']}** obtiene el "
        f"puntaje más bajo (**{ultimo['Puntaje total']:.2f}**)."
    )

    # Factor con mayor brecha entre el líder y el resto
    empresa_propia = companies[0]
    if lider["Competidor"] != empresa_propia:
        brechas = ponderados[["factor"]].copy()
        brechas["brecha"] = ponderados[f"pond_{lider['Competidor']}"] - ponderados[f"pond_{empresa_propia}"]
        peor = brechas.sort_values("brecha", ascending=False).iloc[0]
        if peor["brecha"] > 0:
            st.markdown(
                f"- Frente al líder, **{empresa_propia}** presenta su mayor brecha en "
                f"*'{peor['factor']}'* — este es el factor donde debería enfocar su mejora competitiva."
            )
    else:
        st.markdown(f"- **{empresa_propia}** (asumido como la empresa propia) es actualmente el líder del sector según los factores evaluados.")


# ====================================================================
# 6. MATRIZ ASSNOF / ANSOFF
# ====================================================================

def tab_ansoff():
    st.header("📈 Matriz ASSNOF / Ansoff (Estrategias de Crecimiento)")
    st.caption(
        "Edita las iniciativas de cada cuadrante y asigna una **prioridad (1 = baja, 5 = muy alta)** "
        "para ver qué estrategia de crecimiento conviene enfatizar."
    )

    data = init_state("ansoff", lambda: load_json("ansoff"))
    reset_button("ansoff", lambda: load_json("ansoff"),
                  widget_keys=["editor_ansoff_", "ansoff_priority"])

    if "ansoff_priority" not in st.session_state:
        st.session_state["ansoff_priority"] = {
            k: [3] * len(v["items"]) for k, v in data.items()
        }

    quad_titles = {
        "penetracion": "1️⃣ Penetración de Mercado (mercados actuales / productos actuales)",
        "desarrollo_mercado": "2️⃣ Desarrollo de Mercado (nuevos mercados / productos actuales)",
        "desarrollo_producto": "3️⃣ Desarrollo de Producto (mercados actuales / nuevos productos)",
        "diversificacion": "4️⃣ Diversificación (nuevos mercados / nuevos productos)",
    }

    cols = st.columns(2)
    promedios = {}
    for i, key in enumerate(quad_titles):
        with cols[i % 2]:
            st.subheader(quad_titles[key])
            items = data[key]["items"]
            df = pd.DataFrame({
                "Iniciativa": items,
                "Prioridad": st.session_state["ansoff_priority"][key],
            })
            edited = st.data_editor(
                df, key=f"editor_ansoff_{key}", num_rows="dynamic", use_container_width=True,
                column_config={
                    "Iniciativa": st.column_config.TextColumn("Iniciativa", width="large"),
                    "Prioridad": st.column_config.SelectboxColumn("Prioridad", options=[1, 2, 3, 4, 5]),
                },
                hide_index=True,
            )
            promedios[key] = edited["Prioridad"].mean() if len(edited) else 0
            # Persistir iniciativas y prioridades (antes se perdían al cambiar de pestaña)
            st.session_state["ansoff"][key]["items"] = edited["Iniciativa"].tolist()
            st.session_state["ansoff_priority"][key] = edited["Prioridad"].tolist()

    st.subheader("🧭 Interpretación")
    df_prom = pd.DataFrame({
        "Cuadrante": [quad_titles[k].split(" ", 1)[1] for k in quad_titles],
        "Prioridad promedio": [promedios[k] for k in quad_titles],
    })
    df_prom["Evaluación"] = df_prom["Prioridad promedio"].apply(
        lambda v: clasificar_bmm(v, umbral_bueno=4.0, umbral_medio=2.5)
    )
    df_prom = df_prom.sort_values("Prioridad promedio", ascending=False)
    st.dataframe(df_prom, use_container_width=True, hide_index=True)

    fig = px.bar(df_prom, x="Cuadrante", y="Prioridad promedio", color="Cuadrante",
                 title="Prioridad promedio por estrategia de crecimiento")
    fig.update_layout(showlegend=False, height=380)
    st.plotly_chart(fig, use_container_width=True)

    top = df_prom.iloc[0]
    st.markdown(
        f"La estrategia de crecimiento con **mayor prioridad promedio** es "
        f"**{top['Cuadrante']}** ({top['Prioridad promedio']:.1f}/5). Según la matriz de Ansoff, "
        "esta debería concentrar los recursos estratégicos del siguiente periodo."
    )
    bottom = df_prom.iloc[-1]
    st.markdown(
        f"Por el contrario, **{bottom['Cuadrante']}** tiene la prioridad más baja "
        f"({bottom['Prioridad promedio']:.1f}/5) y puede postergarse o mantenerse solo en observación."
    )


# ====================================================================
# 7. MATRIZ DE RIESGOS
# ====================================================================

RISK_MATRIX = {
    ("Baja", "Menor"): "Riesgo Bajo",
    ("Baja", "Moderada"): "Riesgo Bajo",
    ("Baja", "Mayor"): "Riesgo Tolerable",
    ("Media", "Menor"): "Riesgo Bajo",
    ("Media", "Moderada"): "Riesgo Tolerable",
    ("Media", "Mayor"): "Riesgo Alto",
    ("Alta", "Menor"): "Riesgo Tolerable",
    ("Alta", "Moderada"): "Riesgo Alto",
    ("Alta", "Mayor"): "Riesgo Extremo",
}
RISK_COLOR = {
    "Riesgo Bajo": "#2E9E5B",
    "Riesgo Tolerable": "#F0C420",
    "Riesgo Alto": "#F0883E",
    "Riesgo Extremo": "#D9534F",
}


def tab_riesgos():
    st.header("⚠️ Matriz de Riesgos")
    st.caption(
        "Edita **Probabilidad** y **Consecuencia** de cada evento — el **Nivel de Riesgo** se "
        "calcula automáticamente con la matriz de riesgo estándar (Probabilidad × Consecuencia)."
    )

    with st.expander("Ver matriz de riesgo utilizada"):
        mat_df = pd.DataFrame(
            [[RISK_MATRIX[(p, c)] for c in ["Menor", "Moderada", "Mayor"]] for p in ["Baja", "Media", "Alta"]],
            index=["Baja", "Media", "Alta"], columns=["Menor", "Moderada", "Mayor"],
        )
        st.dataframe(mat_df, use_container_width=True)

    def _normalizar_probabilidad(v):
        t = str(v).strip().lower()
        if t.startswith("baja"):
            return "Baja"
        if t.startswith("medi"):  # cubre "Media", "Medio", "Medios de comunicación", etc.
            return "Media"
        if t.startswith("alta"):
            return "Alta"
        return v

    data = init_state("riesgos", lambda: load_json("riesgos"))
    for r in data:
        r["probabilidad"] = _normalizar_probabilidad(r["probabilidad"])
    reset_button("riesgos", lambda: load_json("riesgos"), widget_keys=["editor_riesgos"])

    df = pd.DataFrame(data)[["evento", "probabilidad", "consecuencia"]]
    edited = st.data_editor(
        df, key="editor_riesgos", num_rows="dynamic", use_container_width=True,
        column_config={
            "evento": st.column_config.TextColumn("Evento de riesgo", width="large"),
            "probabilidad": st.column_config.SelectboxColumn("Probabilidad", options=["Baja", "Media", "Alta"]),
            "consecuencia": st.column_config.SelectboxColumn("Consecuencia", options=["Menor", "Moderada", "Mayor"]),
        },
    )
    edited["probabilidad"] = edited["probabilidad"].apply(_normalizar_probabilidad)

    # Persistir eventos/probabilidad/consecuencia editados (antes se perdían)
    st.session_state["riesgos"] = edited.to_dict("records")

    edited["nivel"] = edited.apply(
        lambda r: RISK_MATRIX.get((r["probabilidad"], r["consecuencia"]), "N/D"), axis=1
    )
    NIVEL_A_EVALUACION = {
        "Riesgo Bajo": "🟢 Bueno", "Riesgo Tolerable": "🟡 Medio",
        "Riesgo Alto": "🔴 Malo", "Riesgo Extremo": "🔴 Malo",
    }
    edited["evaluación"] = edited["nivel"].map(NIVEL_A_EVALUACION).fillna("—")

    def color_nivel(val):
        color = RISK_COLOR.get(val, "#999999")
        return f"background-color: {color}; color: white; font-weight: bold;"

    st.subheader("Resultado")
    st.dataframe(
        edited.style.map(color_nivel, subset=["nivel"]),
        use_container_width=True, hide_index=True,
    )

    conteo = edited["nivel"].value_counts().reindex(
        ["Riesgo Extremo", "Riesgo Alto", "Riesgo Tolerable", "Riesgo Bajo"], fill_value=0
    )
    cols = st.columns(4)
    for c, nivel in zip(cols, conteo.index):
        c.metric(nivel, int(conteo[nivel]))

    fig = px.pie(
        names=conteo.index, values=conteo.values,
        color=conteo.index, color_discrete_map=RISK_COLOR,
        title="Distribución de niveles de riesgo",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🧭 Interpretación")
    conteo_eval = edited["evaluación"].value_counts()
    st.markdown(
        "**Evaluación general según ponderación (Probabilidad × Consecuencia):** "
        + " · ".join(f"{k}: {v}" for k, v in conteo_eval.items())
    )
    n_extremo = int(conteo["Riesgo Extremo"])
    n_alto = int(conteo["Riesgo Alto"])
    total = len(edited)
    if n_extremo > 0:
        eventos_extremos = edited.loc[edited["nivel"] == "Riesgo Extremo", "evento"].tolist()
        st.markdown(
            f"Existen **{n_extremo} riesgo(s) extremo(s)** de un total de {total}: "
            + ", ".join(f"*{e}*" for e in eventos_extremos)
            + ". Estos requieren **planes de mitigación inmediatos** y seguimiento del comité de "
            "riesgos, ya que combinan alta probabilidad con consecuencias mayores."
        )
    if n_alto > 0:
        st.markdown(
            f"Hay **{n_alto} riesgo(s) alto(s)** que deben incluirse en el plan de contingencia "
            "de mediano plazo, aunque no exigen acción inmediata."
        )
    if n_extremo == 0 and n_alto == 0:
        st.markdown(
            "Con la configuración actual **no hay riesgos extremos ni altos**: el perfil de riesgo "
            "de la organización es manejable con controles rutinarios."
        )


# ====================================================================
# 8. FODA NUMÉRICO
# ====================================================================

def tab_foda_numerico():
    st.header("🔢 FODA Numérico (Matriz de Impacto Cruzado)")
    st.caption(
        "Cada celda mide la relación entre una Fortaleza/Debilidad y una Oportunidad/Amenaza: "
        "**0 = sin relación, 0.5 = relación media, 1 = relación fuerte.** Los promedios se recalculan "
        "automáticamente y señalan los cruces estratégicos más relevantes."
    )

    data = init_state("foda", lambda: load_json("foda_numerico"))
    reset_button("foda", lambda: load_json("foda_numerico"),
                  widget_keys=["editor_fo", "editor_fa", "editor_do", "editor_da"])

    o_labels = data["o_labels"]
    a_labels = data["a_labels"]
    # F1-F10 / D1-D10: mismos factores que Holmes y EFI, vía el registro maestro
    # (si renombras un factor en Holmes o EFI, el nombre cambia aquí también).
    fort_codigos = data["fort_codigos"]
    deb_codigos = data["deb_codigos"]
    fort_labels = [f"{factor_nombre('F', c)} {c}" for c in fort_codigos]
    deb_labels = [f"{factor_nombre('D', c)} {c}" for c in deb_codigos]

    def editable_matrix(key, row_labels, col_labels, matrix_key):
        df = pd.DataFrame(data[matrix_key], index=row_labels, columns=col_labels)
        col_config = {c: st.column_config.SelectboxColumn(c, options=[0, 0.5, 1]) for c in col_labels}
        edited = st.data_editor(df, key=key, use_container_width=True, column_config=col_config)

        # Persistir la matriz editada (antes se perdía al cambiar de sub-pestaña)
        st.session_state["foda"][matrix_key] = edited.to_numpy().tolist()

        # Vista con el PROMEDIO integrado, igual que en el Excel original
        # (columna PROMEDIO = fila M/X, fila PROMEDIO = fila B13/B25)
        vista = edited.copy()
        vista["PROMEDIO"] = vista.mean(axis=1)
        fila_promedio = vista.mean(axis=0)
        fila_promedio.name = "PROMEDIO"
        vista = pd.concat([vista, fila_promedio.to_frame().T])
        st.caption("Vista con el PROMEDIO por fila y por columna (igual que en el Excel original):")
        st.dataframe(vista.style.format("{:.2f}"), use_container_width=True)

        return edited

    sub = st.tabs(["FO (Fortalezas–Oportunidades)", "FA (Fortalezas–Amenazas)",
                   "DO (Debilidades–Oportunidades)", "DA (Debilidades–Amenazas)"], key="tabs_foda_numerico")

    with sub[0]:
        st.write("Estrategias **ofensivas**: usar fortalezas para aprovechar oportunidades.")
        fo = editable_matrix("editor_fo", fort_labels, o_labels, "fort_vs_o")
    with sub[1]:
        st.write("Estrategias **defensivas**: usar fortalezas para neutralizar amenazas.")
        fa = editable_matrix("editor_fa", fort_labels, a_labels, "fort_vs_a")
    with sub[2]:
        st.write("Estrategias **adaptativas**: superar debilidades aprovechando oportunidades.")
        do = editable_matrix("editor_do", deb_labels, o_labels, "deb_vs_o")
    with sub[3]:
        st.write("Estrategias de **supervivencia**: reducir debilidades y evitar amenazas.")
        da = editable_matrix("editor_da", deb_labels, a_labels, "deb_vs_a")

    def row_avg(df):
        return df.mean(axis=1)

    def col_avg(df):
        return df.mean(axis=0)

    resumen_filas = pd.DataFrame({
        "FO": row_avg(fo), "FA": row_avg(fa),
    }).reindex(fort_labels)
    resumen_filas_d = pd.DataFrame({
        "DO": row_avg(do), "DA": row_avg(da),
    }).reindex(deb_labels)

    resumen_cols_pos = pd.DataFrame({
        "vs Fortalezas (FO)": col_avg(fo), "vs Debilidades (DO)": col_avg(do),
    }).reindex(o_labels)
    resumen_cols_neg = pd.DataFrame({
        "vs Fortalezas (FA)": col_avg(fa), "vs Debilidades (DA)": col_avg(da),
    }).reindex(a_labels)

    def _con_evaluacion(df_resumen):
        out = df_resumen.copy()
        out["Promedio"] = out.mean(axis=1)
        out["Evaluación"] = out["Promedio"].apply(
            lambda v: clasificar_bmm(v, umbral_bueno=0.66, umbral_medio=0.33)
        )
        return out

    resumen_filas = _con_evaluacion(resumen_filas)
    resumen_filas_d = _con_evaluacion(resumen_filas_d)
    resumen_cols_pos = _con_evaluacion(resumen_cols_pos)
    resumen_cols_neg = _con_evaluacion(resumen_cols_neg)

    st.subheader("📊 Promedios por factor")
    st.caption(
        "🔗 Evaluación por ponderación: 🟢 Bueno (≥0.66) · 🟡 Medio (0.33-0.66) · 🔴 Malo (<0.33)."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fortalezas** (promedio de relación con O y A)")
        st.dataframe(resumen_filas.style.format("{:.2f}", subset=["FO", "FA", "Promedio"]), use_container_width=True)
        st.markdown("**Debilidades** (promedio de relación con O y A)")
        st.dataframe(resumen_filas_d.style.format("{:.2f}", subset=["DO", "DA", "Promedio"]), use_container_width=True)
    with c2:
        st.markdown("**Oportunidades** (promedio de relación con F y D)")
        st.dataframe(
            resumen_cols_pos.style.format(
                "{:.2f}", subset=["vs Fortalezas (FO)", "vs Debilidades (DO)", "Promedio"]
            ),
            use_container_width=True,
        )
        st.markdown("**Amenazas** (promedio de relación con F y D)")
        st.dataframe(
            resumen_cols_neg.style.format(
                "{:.2f}", subset=["vs Fortalezas (FA)", "vs Debilidades (DA)", "Promedio"]
            ),
            use_container_width=True,
        )

    st.subheader("🧭 Interpretación")

    top_fo_factor = resumen_filas["FO"].idxmax()
    top_fo_val = resumen_filas["FO"].max()
    top_da_factor = resumen_filas_d["DA"].idxmax()
    top_da_val = resumen_filas_d["DA"].max()
    top_o = resumen_cols_pos["Promedio"].idxmax()
    top_a = resumen_cols_neg["Promedio"].idxmax()

    st.markdown(
        f"- La fortaleza con mayor potencial **ofensivo (FO)** es *{top_fo_factor}* "
        f"(promedio {top_fo_val:.2f}) — es la mejor palanca para capturar oportunidades."
    )
    st.markdown(
        f"- La debilidad más expuesta en clave de **supervivencia (DA)** es *{top_da_factor}* "
        f"(promedio {top_da_val:.2f}) — combina alta vulnerabilidad con amenazas relevantes; "
        "requiere un plan de contingencia prioritario."
    )
    st.markdown(
        f"- La oportunidad *{top_o}* es, en promedio, la que mejor conecta con las capacidades "
        f"internas de la organización (fortalezas y debilidades)."
    )
    st.markdown(
        f"- La amenaza *{top_a}* es la que en promedio más interactúa con el perfil interno actual, "
        "por lo que merece vigilancia prioritaria."
    )

    promedio_global_fo = resumen_filas["FO"].mean()
    promedio_global_da = resumen_filas_d["DA"].mean()
    if promedio_global_fo > promedio_global_da:
        st.info(
            "En conjunto, el perfil estratégico está **más orientado al ataque (FO)** que a la "
            "defensa (DA): la organización está en mejor posición para crecer que para protegerse."
        )
    else:
        st.info(
            "En conjunto, el perfil estratégico está **más orientado a la defensa/supervivencia (DA)** "
            "que al ataque (FO): conviene primero blindar las debilidades críticas antes de expandirse."
        )


# ====================================================================
# I. MÓDULO SEGUIMIENTO Y CONTROL (Gráficas de Medias + CMI con semáforo)
# ====================================================================

SEMAFORO_INFO = {
    "Cumplido":    {"color": "#2E9E5B", "icono": "🟢", "umbral": "≥ 90%"},
    "En riesgo":   {"color": "#F0C420", "icono": "🟡", "umbral": "70% – 89%"},
    "No cumplido": {"color": "#D9534F", "icono": "🔴", "umbral": "< 70%"},
}


def calcular_semaforo(cumplimiento):
    if cumplimiento >= 90:
        return "Cumplido"
    elif cumplimiento >= 70:
        return "En riesgo"
    return "No cumplido"


def _bullet_chart(resultado, meta, ucl, central, lcl):
    rango_max = max(120, ucl + 10, meta + 10)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=resultado,
        number={"suffix": "%", "font": {"size": 22}},
        delta={"reference": central, "suffix": "%"},
        gauge={
            "shape": "bullet",
            "axis": {"range": [0, rango_max]},
            "threshold": {
                "line": {"color": "black", "width": 3},
                "thickness": 0.8,
                "value": central,
            },
            "steps": [
                {"range": [0, lcl], "color": "#F5B7B1"},
                {"range": [lcl, ucl], "color": "#ABEBC6"},
                {"range": [ucl, rango_max], "color": "#F5B7B1"},
            ],
            "bar": {"color": "#2E4053", "thickness": 0.5},
        },
    ))
    fig.update_layout(height=110, margin=dict(l=10, r=10, t=25, b=10))
    return fig


# ====================================================================
# J. MÓDULO CMI (Estrategias 1-12 -> Cuadro de Mando Integral oficial)
# ====================================================================

def _calcular_estrategia(e):
    """Devuelve (kpis_por_anio, promedio, rango, lcs, lcc, lci) para una Estrategia."""
    a2 = e["constante_a2"]
    if e["tipo"] == "departamentos":
        x_bar_anual = [sum(v) / len(v) for v in e["valores"]]
        r_anual = [max(v) - min(v) for v in e["valores"]]
        promedio = sum(x_bar_anual) / len(x_bar_anual)
        rango = sum(r_anual) / len(r_anual)
        kpis = x_bar_anual
    else:
        if e["tipo"] == "simple":
            kpis = [n / d if d else 0 for n, d in zip(e["numerador"], e["denominador"])]
        else:  # suma
            kpis = [sum(n) / sum(d) if sum(d) else 0 for n, d in zip(e["numerador"], e["denominador"])]
        promedio = sum(kpis) / len(kpis)
        rango = max(kpis) - min(kpis)

    lcc = promedio
    lcs = promedio + a2 * rango
    lci = max(0.0, promedio - a2 * rango)
    return kpis, promedio, rango, lcs, lcc, lci


def calcular_todos_resultados_estrategias():
    """Calcula (sin dibujar nada) el resultado del último año de las 12 Estrategias, para que
    cualquier pestaña (Mapa Estratégico, Gráficas de Medias, CMI Oficial) tenga el dato fresco
    sin depender de que el usuario haya visitado antes la pestaña 📐 Estrategias 1-12."""
    estrategias = init_state("estrategias_kpi", lambda: load_json("estrategias_kpi"))
    resultados = {}
    for e in estrategias:
        kpis, *_ = _calcular_estrategia(e)
        resultados[e["id"]] = kpis[-1]
    st.session_state["cmi_resultados_desde_estrategias"] = resultados
    return resultados


def _editor_estrategia(e, idx):
    """Muestra y edita los datos históricos de una Estrategia; devuelve el KPI del último año (0-1)."""
    if e["tipo"] == "departamentos":
        df = pd.DataFrame(e["valores"], index=e["anios"], columns=e["departamentos"])
        df = df * 100  # mostrar en %
        edited = st.data_editor(
            df, key=f"estr_dep_{idx}", use_container_width=True,
            column_config={c: NUM_COL(c, min_value=0.0, max_value=150.0, step=0.5, format="%.1f")
                            for c in e["departamentos"]},
        )
        nuevos_valores = (edited.to_numpy() / 100).tolist()
        st.session_state["estrategias_kpi"][idx]["valores"] = nuevos_valores
        e = dict(e); e["valores"] = nuevos_valores

    elif e["tipo"] == "simple":
        df = pd.DataFrame({
            "Año": e["anios"],
            e["numerador_label"]: e["numerador"],
            e["denominador_label"]: e["denominador"],
        })
        edited = st.data_editor(
            df, key=f"estr_simple_{idx}", use_container_width=True, hide_index=True,
            column_config={
                "Año": st.column_config.NumberColumn("Año", disabled=True),
                e["numerador_label"]: NUM_COL(e["numerador_label"], min_value=0.0, step=1.0),
                e["denominador_label"]: NUM_COL(e["denominador_label"], min_value=0.01, step=1.0),
            },
        )
        st.session_state["estrategias_kpi"][idx]["numerador"] = edited[e["numerador_label"]].tolist()
        st.session_state["estrategias_kpi"][idx]["denominador"] = edited[e["denominador_label"]].tolist()
        e = dict(e)
        e["numerador"] = edited[e["numerador_label"]].tolist()
        e["denominador"] = edited[e["denominador_label"]].tolist()

    else:  # suma
        cols = {"Año": e["anios"]}
        for i, lab in enumerate(e["numerador_labels"]):
            cols[f"➕ {lab}"] = [row[i] for row in e["numerador"]]
        for i, lab in enumerate(e["denominador_labels"]):
            cols[f"➗ {lab}"] = [row[i] for row in e["denominador"]]
        df = pd.DataFrame(cols)
        col_config = {"Año": st.column_config.NumberColumn("Año", disabled=True)}
        for c in df.columns:
            if c != "Año":
                col_config[c] = NUM_COL(c, min_value=0.0, step=1.0)
        edited = st.data_editor(df, key=f"estr_suma_{idx}", use_container_width=True,
                                 hide_index=True, column_config=col_config)
        n_num = len(e["numerador_labels"])
        n_den = len(e["denominador_labels"])
        nuevo_num = edited[[f"➕ {lab}" for lab in e["numerador_labels"]]].to_numpy().tolist()
        nuevo_den = edited[[f"➗ {lab}" for lab in e["denominador_labels"]]].to_numpy().tolist()
        st.session_state["estrategias_kpi"][idx]["numerador"] = nuevo_num
        st.session_state["estrategias_kpi"][idx]["denominador"] = nuevo_den
        e = dict(e); e["numerador"] = nuevo_num; e["denominador"] = nuevo_den

    return e


def tab_cmi_estrategias():
    st.subheader("📐 Estrategias 1 a 12 — Cálculo de KPIs y gráfica de medias")
    st.caption(
        "Cada Estrategia trae su serie histórica editable, con la que se recalculan el "
        "**Promedio**, el **Rango**, y los límites de control (LCS/LCC/LCI). El valor del "
        "**último año** de cada Estrategia alimenta directamente el **Resultado** de su "
        "indicador correspondiente en la pestaña 🚦 Cuadro de Mando Integral."
    )

    if "estrategias_kpi" not in st.session_state:
        st.session_state["estrategias_kpi"] = json.loads(json.dumps(load_json("estrategias_kpi")))

    if st.button("↩️ Restaurar valores originales", key="reset_estrategias_kpi"):
        st.session_state["estrategias_kpi"] = json.loads(json.dumps(load_json("estrategias_kpi")))
        _purge_widget_state(["estr_dep_", "estr_simple_", "estr_suma_", "interp_estr_"])
        st.rerun()

    ultimos_valores = {}

    for idx, e in enumerate(st.session_state["estrategias_kpi"]):
        color = PERSPECTIVA_COLOR.get(e["perspectiva"], "#999999")
        with st.expander(f"**{e['id']}** — {e['kpi_cmi_match']}", expanded=(idx == 0)):
            st.markdown(
                f"<span style='background-color:{color};color:white;padding:2px 10px;"
                f"border-radius:12px;font-size:0.8em;'>{e['perspectiva']}</span> "
                f"&nbsp; Muestra: n={e['muestra_n']} &nbsp; Constante A2: {e['constante_a2']}",
                unsafe_allow_html=True,
            )
            st.markdown(f"➡️ **Alimenta en el CMI a:** *{e['kpi_cmi_match']}*")

            e_actualizada = _editor_estrategia(e, idx)
            kpis, promedio, rango, lcs, lcc, lci = _calcular_estrategia(e_actualizada)
            ultimo = kpis[-1]
            ultimos_valores[e["id"]] = ultimo

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Promedio", f"{promedio*100:.1f}%")
            c2.metric("Rango", f"{rango*100:.1f} pts")
            c3.metric("Último valor (→ CMI)", f"{ultimo*100:.1f}%")
            c4.metric("Banda de control", f"{lci*100:.1f}% – {lcs*100:.1f}%")

            anios_x = e_actualizada["anios"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=anios_x, y=[k*100 for k in kpis], mode="lines+markers",
                                      name="KPI anual", line=dict(color="#2E4053", width=3)))
            fig.add_hline(y=lcs*100, line_dash="dash", line_color="#D9534F", annotation_text="LCS")
            fig.add_hline(y=lcc*100, line_dash="dot", line_color="#2E9E5B", annotation_text="LCC (Promedio)")
            fig.add_hline(y=lci*100, line_dash="dash", line_color="#D9534F", annotation_text="LCI")
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10),
                               yaxis_title="KPI (%)", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_estr_{idx}")

            interpretacion = st.text_area("Interpretación", value=e["interpretacion"], height=90,
                                           key=f"interp_estr_{idx}")
            st.session_state["estrategias_kpi"][idx]["interpretacion"] = interpretacion

    st.session_state["cmi_resultados_desde_estrategias"] = ultimos_valores


def tab_cmi_oficial():
    st.subheader("🚦 Cuadro de Mando Integral")
    st.caption(
        "Edita **Perspectiva, Plan, Indicador, Fórmula, Meta y Responsable** directamente en la "
        "tabla. El **Resultado** no se edita aquí: se toma automáticamente del último año "
        "calculado en 📐 Estrategias 1-12 (según la fórmula real de cada indicador), y el **% de "
        "Cumplimiento** y el **semáforo** se recalculan de inmediato. 🔗 También alimenta las "
        "tarjetas de 📈 Gráficas de Medias (Seguimiento y Control) y el resumen por objetivo del "
        "🗺️ Mapa Estratégico."
    )

    data = init_state("cmi_oficial", lambda: load_json("cmi_oficial"))
    reset_button("cmi_oficial", lambda: load_json("cmi_oficial"), widget_keys=["editor_cmi_oficial"])

    resultados = calcular_todos_resultados_estrategias()

    df = pd.DataFrame(data)
    # 🔗 El objetivo mostrado viene siempre de la pestaña 🏁 Objetivos (fuente única)
    df["objetivo"] = [objetivo_texto(row.get("objetivo_id"), fallback=row["objetivo"]) for row in data]
    df["resultado"] = [round(resultados.get(row.get("estrategia_id"), 0.0) * 100, 2) for row in data]

    cols_editor = ["perspectiva", "objetivo", "plan", "indicador", "formula", "meta", "resultado", "responsable"]
    edited = st.data_editor(
        df[cols_editor], key="editor_cmi_oficial", num_rows="fixed", use_container_width=True, hide_index=True,
        column_config={
            "perspectiva": st.column_config.SelectboxColumn("Perspectiva", options=list(PERSPECTIVA_COLOR.keys())),
            "objetivo": st.column_config.TextColumn(
                "Objetivo estratégico (🔗 desde pestaña Objetivos)", width="medium", disabled=True
            ),
            "plan": st.column_config.TextColumn("Estrategia / Plan", width="large"),
            "indicador": st.column_config.TextColumn("Indicador (KPI)", width="medium"),
            "formula": st.column_config.TextColumn("Fórmula", width="large"),
            "meta": NUM_COL("Meta (%)", min_value=0.0, max_value=200.0, step=1.0),
            "resultado": NUM_COL("Resultado (%) — 🔗 desde Estrategias", disabled=True, format="%.2f"),
            "responsable": st.column_config.TextColumn("Responsable", width="medium"),
        },
        height=460,
    )

    # Persistir ediciones (objetivo_id, estrategia_id, ucl/lcl/central no se editan aquí, se conservan)
    for i, row in edited.iterrows():
        st.session_state["cmi_oficial"][i]["perspectiva"] = row["perspectiva"]
        st.session_state["cmi_oficial"][i]["plan"] = row["plan"]
        st.session_state["cmi_oficial"][i]["indicador"] = row["indicador"]
        st.session_state["cmi_oficial"][i]["formula"] = row["formula"]
        st.session_state["cmi_oficial"][i]["meta"] = row["meta"]
        st.session_state["cmi_oficial"][i]["responsable"] = row["responsable"]

    df = edited.copy()
    df["cumplimiento"] = df.apply(lambda r: (r["resultado"] / r["meta"] * 100) if r["meta"] else 0.0, axis=1)
    df["semaforo"] = df["cumplimiento"].apply(calcular_semaforo)
    df["🚦"] = df["semaforo"].apply(lambda s: SEMAFORO_INFO[s]["icono"])

    def color_fila(row):
        color = SEMAFORO_INFO[row["semaforo"]]["color"]
        return [f"background-color:{color};color:white;font-weight:bold;" if col in ("cumplimiento", "🚦") else ""
                for col in row.index]

    show_cols = ["🚦", "perspectiva", "objetivo", "plan", "indicador", "formula", "meta", "resultado",
                 "cumplimiento", "semaforo", "responsable"]
    show_df = df[show_cols].copy()
    show_df["meta"] = show_df["meta"].round(1)
    show_df["resultado"] = show_df["resultado"].round(1)
    show_df["cumplimiento"] = show_df["cumplimiento"].round(1)

    st.dataframe(show_df.style.apply(color_fila, axis=1), use_container_width=True,
                 hide_index=True, height=460)

    conteo = df["semaforo"].value_counts().reindex(["Cumplido", "En riesgo", "No cumplido"], fill_value=0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cumplimiento promedio", f"{df['cumplimiento'].mean():.1f}%")
    c2.metric("🟢 Cumplido", int(conteo["Cumplido"]))
    c3.metric("🟡 En riesgo", int(conteo["En riesgo"]))
    c4.metric("🔴 No cumplido", int(conteo["No cumplido"]))

    resumen_persp = df.groupby("perspectiva")["cumplimiento"].mean().reset_index()
    fig = px.bar(resumen_persp, x="perspectiva", y="cumplimiento", color="perspectiva",
                 color_discrete_map=PERSPECTIVA_COLOR, title="Cumplimiento promedio por perspectiva")
    fig.add_hline(y=90, line_dash="dash", line_color="green", annotation_text="Umbral 'Cumplido' (90%)")
    fig.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Umbral 'En riesgo' (70%)")
    fig.update_layout(showlegend=False, height=380, yaxis_title="% Cumplimiento")
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.pie(names=conteo.index, values=conteo.values, color=conteo.index,
                  color_discrete_map={k: v["color"] for k, v in SEMAFORO_INFO.items()},
                  title="Distribución del semáforo (12 indicadores)")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("🧭 Interpretación")
    if int(conteo["No cumplido"]) > 0:
        criticos = df.loc[df["semaforo"] == "No cumplido", "indicador"].tolist()
        st.markdown(
            f"Hay **{int(conteo['No cumplido'])} indicador(es) en rojo**: "
            + ", ".join(f"*{c}*" for c in criticos)
            + ". Ajusta sus valores históricos en la pestaña de Estrategias para simular planes de "
            "mejora y ver el efecto inmediato en este semáforo."
        )
    peor_persp = resumen_persp.sort_values("cumplimiento").iloc[0]
    st.markdown(
        f"La perspectiva con **menor cumplimiento promedio** es **{peor_persp['perspectiva']}** "
        f"({peor_persp['cumplimiento']:.1f}%)."
    )
    st.info(
        "💡 Prueba esto: ve a la pestaña 📐 Estrategias 1-12, cambia cualquier valor histórico de "
        "un indicador (por ejemplo, el año más reciente) y vuelve a esta pestaña — el Resultado, "
        "el % de Cumplimiento y el semáforo ya estarán actualizados."
    )


def tab_cmi():
    st.header("🚦 CMI — Cuadro de Mando Integral")
    st.caption(
        "Módulo basado en el Anexo de Estrategias (Estrategia 1 a 12) y el Cuadro de Mando "
        "Integral oficial de Floral Chain Group. **Las dos pestañas están enlazadas**: el "
        "Resultado de cada indicador del CMI proviene directamente del cálculo hecho en su "
        "Estrategia correspondiente."
    )
    sub = st.tabs(["📐 Estrategias 1-12", "🚦 Cuadro de Mando Integral"], key="tabs_cmi")
    with sub[0]:
        tab_cmi_estrategias()
    with sub[1]:
        tab_cmi_oficial()


# ====================================================================
# J. MÓDULO EFECTOS DE LA INVERSIÓN (5 pestañas interconectadas)
# ====================================================================

def irr_bisection(cashflows, lo=-0.99, hi=10.0, iters=200):
    """TIR por bisección sobre VAN(r)=0. Devuelve None si no hay cambio de signo."""
    def npv(r):
        return sum(cf / (1 + r) ** i for i, cf in enumerate(cashflows))
    npv_lo, npv_hi = npv(lo), npv(hi)
    if npv_lo * npv_hi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


SEMAFORO_VIABILIDAD = {
    "VERDE":   {"color": "#2E9E5B", "icono": "🟢", "estado": "Proyecto viable y con buen margen"},
    "NARANJA": {"color": "#F0C420", "icono": "🟠", "estado": "Proyecto viable pero con margen ajustado"},
    "ROJO":    {"color": "#D9534F", "icono": "🔴", "estado": "Proyecto no viable financieramente"},
}


def calcular_semaforo_viabilidad(van, bc):
    if van > 0 and bc >= 1.1:
        return "VERDE"
    elif van > 0 and 1.0 <= bc < 1.1:
        return "NARANJA"
    return "ROJO"


def calc_efectos_inversion(data):
    """Recalcula TODO el modelo (Tabla 14, 15, 16 y PRI) a partir de los supuestos editables.
    Es la única función que hace los cálculos -- las 5 pestañas solo leen de aquí, por eso
    cualquier cambio se refleja automáticamente en todas ellas."""
    anios = data["anios"]
    n = len(anios)
    ingresos = data["ingresos"]
    ratio_costo = data["ratio_costo_ventas"]
    costos = [ing * ratio_costo for ing in ingresos]
    utilidad_bruta = [i - c for i, c in zip(ingresos, costos)]

    gastos_admin = []
    base = data["gasto_admin_base"]
    infl = data["inflacion_admin"]
    for i in range(n):
        gastos_admin.append(base if i == 0 else gastos_admin[-1] * (1 + infl))

    ahorro_pct = data["ahorro_pct"]
    ahorro = [ing * a for ing, a in zip(ingresos, ahorro_pct)]

    deprec = [data["depreciacion_anual"]] * n
    utilidad_operativa = [ub - ga + ah - d for ub, ga, ah, d in
                           zip(utilidad_bruta, gastos_admin, ahorro, deprec)]

    gfin = [data["gastos_financieros_anual"]] * n
    uai = [uo - g for uo, g in zip(utilidad_operativa, gfin)]
    ptu = [u * data["ptu_pct"] for u in uai]
    uair = [u - p for u, p in zip(uai, ptu)]
    ir = [u * data["ir_pct"] for u in uair]
    utilidad_neta = [u - i for u, i in zip(uair, ir)]

    fne = [-data["inversion_inicial"]] + [un + d for un, d in zip(utilidad_neta, deprec)]
    acumulado = [fne[0]]
    for f in fne[1:]:
        acumulado.append(acumulado[-1] + f)

    tmar = data["tmar"]
    factor_desc = [1 / (1 + tmar) ** (i + 1) for i in range(n)]
    va_fne = [f * fd for f, fd in zip(fne[1:], factor_desc)]
    suma_va = sum(va_fne)
    van = suma_va - data["inversion_inicial"]
    bc = suma_va / data["inversion_inicial"] if data["inversion_inicial"] else 0
    tir = irr_bisection(fne)

    a = sum(1 for x in acumulado[1:] if x < 0)
    if a >= n:
        pri_anios, inv_no_recuperada, fne_recuperacion = None, None, None
    else:
        inv_no_recuperada = -acumulado[a]
        fne_recuperacion = fne[a + 1]
        pri_anios = a + (inv_no_recuperada / fne_recuperacion if fne_recuperacion else 0)

    return {
        "anios": anios, "ingresos": ingresos, "costos": costos, "utilidad_bruta": utilidad_bruta,
        "gastos_admin": gastos_admin, "ahorro_pct": ahorro_pct, "ahorro": ahorro, "depreciacion": deprec,
        "utilidad_operativa": utilidad_operativa, "gastos_financieros": gfin, "uai": uai, "ptu": ptu,
        "uair": uair, "ir": ir, "utilidad_neta": utilidad_neta, "fne": fne, "acumulado": acumulado,
        "factor_descuento": factor_desc, "va_fne": va_fne, "suma_va": suma_va, "van": van, "bc": bc,
        "tir": tir, "a": a, "pri_anios": pri_anios,
        "inv_no_recuperada": inv_no_recuperada, "fne_recuperacion": fne_recuperacion,
    }


def _pri_texto(a, pri_anios):
    if pri_anios is None:
        return "El proyecto NO recupera la inversión dentro del horizonte evaluado."
    meses_totales = (pri_anios - a) * 12
    meses = int(meses_totales)
    dias = round((meses_totales - meses) * 30)
    return f"{a} años, {meses} meses, {dias} días"


def tab_ei_resumen():
    st.subheader("📊 Resumen Ejecutivo")
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    reset_button("efectos_inversion", lambda: load_json("efectos_inversion"), button_key="ei_resumen",
                 widget_keys=EI_TODOS_LOS_WIDGETS)
    r = calc_efectos_inversion(data)

    sem = calcular_semaforo_viabilidad(r["van"], r["bc"])
    info = SEMAFORO_VIABILIDAD[sem]
    st.markdown(
        f"<div style='background-color:{info['color']}22;border:2px solid {info['color']};"
        f"border-radius:10px;padding:14px;margin-bottom:14px;'>"
        f"<span style='font-size:1.4em'>{info['icono']} <b>{sem}</b></span> — {info['estado']}"
        f"</div>", unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Inversión Inicial", f"${data['inversion_inicial']:,.0f}")
    c2.metric("VAN", f"${r['van']:,.0f}")
    c3.metric("TIR", f"{r['tir']*100:.2f}%" if r["tir"] is not None else "N/D")
    c4.metric("B/C", f"{r['bc']:.3f}")
    c5.metric("PRI", _pri_texto(r["a"], r["pri_anios"]) if r["pri_anios"] is not None else "N/D")

    st.caption(
        "🔗 Estos 5 valores vienen de las otras 4 pestañas: Inversión y VAN/B-C de 'Relación B/C', "
        "TIR calculada sobre el mismo flujo de caja, y PRI de 'Período de Recuperación'. Edita "
        "cualquier supuesto en esas pestañas y este resumen se actualiza solo."
    )

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_bar(x=[str(a) for a in r["anios"]], y=r["ingresos"], name="Ingresos", marker_color="#2E9E5B")
        fig.add_bar(x=[str(a) for a in r["anios"]], y=r["costos"], name="Costos", marker_color="#D9534F")
        fig.update_layout(title="Ingresos vs. Costos", barmode="group", height=320,
                           margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch", key="ei_resumen_ing_costos")
    with col2:
        anios_flujo = ["Año 0"] + [str(a) for a in r["anios"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=anios_flujo, y=r["acumulado"], mode="lines+markers",
                                   name="Flujo Acumulado", line=dict(color="#2E4053", width=3)))
        fig2.add_hline(y=0, line_dash="dash", line_color="#999999")
        fig2.update_layout(title="Evolución del Flujo Acumulado", height=320,
                            margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig2, width="stretch", key="ei_resumen_flujo_acum")


EI_TODOS_LOS_WIDGETS = [
    "ei_ingreso_", "ei_ahorro_", "ei_ratio_costo", "ei_gasto_admin_base",
    "ei_inflacion_admin", "ei_deprec_er", "ei_gfin_er", "ei_ptu", "ei_ir",
    "ei_inversion_inicial_fe", "ei_tmar",
]


def tab_ei_estado_resultados():
    st.subheader("📈 Estado de Resultados Proforma")
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    reset_button("efectos_inversion", lambda: load_json("efectos_inversion"), button_key="ei_er",
                 widget_keys=EI_TODOS_LOS_WIDGETS)

    st.markdown("**Ingresos por año (USD) — edítalos aquí:**")
    cols = st.columns(5)
    nuevos_ingresos = []
    for i, (col, anio) in enumerate(zip(cols, data["anios"])):
        v = col.number_input(str(anio), min_value=0.0, value=float(data["ingresos"][i]),
                              step=1000.0, format="%.0f", key=f"ei_ingreso_{i}")
        nuevos_ingresos.append(v)
    data["ingresos"] = nuevos_ingresos

    with st.expander("⚙️ Supuestos del Estado de Resultados"):
        c1, c2 = st.columns(2)
        data["ratio_costo_ventas"] = c1.slider(
            "Ratio Costo de Ventas / Ingresos", 0.0, 1.0, float(data["ratio_costo_ventas"]),
            step=0.0001, format="%.4f", key="ei_ratio_costo")
        data["gasto_admin_base"] = c2.number_input(
            "Gastos Administrativos Año 1 (USD)", min_value=0.0,
            value=float(data["gasto_admin_base"]), step=100.0, key="ei_gasto_admin_base")
        data["inflacion_admin"] = c1.slider(
            "Inflación anual Gastos Administrativos", 0.0, 0.20, float(data["inflacion_admin"]),
            step=0.005, format="%.3f", key="ei_inflacion_admin")
        data["depreciacion_anual"] = c2.number_input(
            "Depreciación / Amortización anual (USD)", min_value=0.0,
            value=float(data["depreciacion_anual"]), step=100.0, key="ei_deprec_er")
        data["gastos_financieros_anual"] = c1.number_input(
            "Gastos Financieros anual (USD)", min_value=0.0,
            value=float(data["gastos_financieros_anual"]), step=100.0, key="ei_gfin_er")
        data["ptu_pct"] = c2.slider("% Participación Trabajadores (PTU)", 0.0, 0.30,
                                    float(data["ptu_pct"]), step=0.01, key="ei_ptu")
        data["ir_pct"] = c1.slider("% Impuesto a la Renta (IR)", 0.0, 0.40,
                                   float(data["ir_pct"]), step=0.01, key="ei_ir")

        st.markdown("**% Ahorro / Beneficio Operativo Neto por año (Objetivo Estratégico 2):**")
        cols_ah = st.columns(5)
        nuevos_ahorro = []
        for i, (col, anio) in enumerate(zip(cols_ah, data["anios"])):
            v = col.slider(str(anio), 0.0, 1.0, float(data["ahorro_pct"][i]), step=0.001,
                           format="%.3f", key=f"ei_ahorro_{i}")
            nuevos_ahorro.append(v)
        data["ahorro_pct"] = nuevos_ahorro

    st.session_state["efectos_inversion"] = data
    r = calc_efectos_inversion(data)

    df = pd.DataFrame({
        "Concepto": ["Ingresos", "(-) Costos", "(=) UTILIDAD BRUTA", "(-) Gastos Administrativos",
                     "(+) Ahorro Operativo Neto", "(-) Depreciación", "(=) UTILIDAD OPERATIVA",
                     "(-) Gastos Financieros", "(=) Utilidad antes de PT e IR",
                     "(-) PTU", "(=) Utilidad antes de IR", "(-) IR", "(=) UTILIDAD NETA"],
    })
    filas = [r["ingresos"], r["costos"], r["utilidad_bruta"], r["gastos_admin"], r["ahorro"],
             r["depreciacion"], r["utilidad_operativa"], r["gastos_financieros"], r["uai"],
             r["ptu"], r["uair"], r["ir"], r["utilidad_neta"]]
    for i, anio in enumerate(data["anios"]):
        df[str(anio)] = [round(fila[i]) for fila in filas]
    st.dataframe(df, width="stretch", hide_index=True, height=460)

    margen_neto = [un / ing * 100 if ing else 0 for un, ing in zip(r["utilidad_neta"], r["ingresos"])]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[str(a) for a in data["anios"]], y=r["utilidad_neta"],
                              name="Utilidad Neta (USD)", yaxis="y1", line=dict(color="#2E9E5B", width=3)))
    fig.add_trace(go.Scatter(x=[str(a) for a in data["anios"]], y=margen_neto,
                              name="Margen Neto (%)", yaxis="y2", line=dict(color="#1F4E78", dash="dot")))
    fig.update_layout(
        title="Evolución de Utilidad Neta y Margen Neto", height=350,
        yaxis=dict(title="USD"), yaxis2=dict(title="%", overlaying="y", side="right"),
        margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, width="stretch", key="ei_er_utilidad_margen")


def tab_ei_flujo_efectivo():
    st.subheader("💰 Flujo de Efectivo")
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    reset_button("efectos_inversion", lambda: load_json("efectos_inversion"), button_key="ei_fe",
                 widget_keys=EI_TODOS_LOS_WIDGETS)

    data["inversion_inicial"] = st.number_input(
        "Inversión inicial — Año 0 (USD)", min_value=0.0, value=float(data["inversion_inicial"]),
        step=1000.0, format="%.0f", key="ei_inversion_inicial_fe")
    st.session_state["efectos_inversion"] = data

    st.caption("🔗 Utilidad Neta y Depreciación vienen automáticamente de la pestaña 'Estado de Resultados'.")
    r = calc_efectos_inversion(data)

    cols_años = ["Año 0"] + [str(a) for a in data["anios"]]
    df = pd.DataFrame({
        "Concepto": ["Inversión inicial", "Utilidad Neta", "(+) Depreciación",
                     "FLUJO NETO DE EFECTIVO (FNE)", "FLUJO ACUMULADO"],
    })
    inv_row = [-data["inversion_inicial"]] + [None] * len(data["anios"])
    uneta_row = [None] + r["utilidad_neta"]
    dep_row = [None] + r["depreciacion"]
    for i, col_name in enumerate(cols_años):
        df[col_name] = [
            f"${inv_row[i]:,.0f}" if inv_row[i] is not None else "-",
            f"${uneta_row[i]:,.0f}" if uneta_row[i] is not None else "-",
            f"${dep_row[i]:,.0f}" if dep_row[i] is not None else "-",
            f"${r['fne'][i]:,.0f}",
            f"${r['acumulado'][i]:,.0f}",
        ]
    st.dataframe(df, width="stretch", hide_index=True, height=220)

    fig = go.Figure()
    fig.add_bar(x=cols_años, y=r["fne"], name="FNE", marker_color="#2E9E5B")
    fig.add_trace(go.Scatter(x=cols_años, y=r["acumulado"], name="Flujo Acumulado",
                              mode="lines+markers", line=dict(color="#1F4E78", width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color="#999999")
    fig.update_layout(title="FNE y Flujo Acumulado", height=350,
                       margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch", key="ei_fe_fne_acum")


def tab_ei_bc():
    st.subheader("📉 Relación Beneficio/Costo — B/C")
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    reset_button("efectos_inversion", lambda: load_json("efectos_inversion"), button_key="ei_bc",
                 widget_keys=EI_TODOS_LOS_WIDGETS)

    data["tmar"] = st.slider("TMAR (tasa mínima aceptable de rendimiento)", 0.0, 0.50,
                              float(data["tmar"]), step=0.005, format="%.3f", key="ei_tmar")
    st.session_state["efectos_inversion"] = data
    st.caption("🔗 El FNE viene automáticamente de la pestaña 'Flujo de Efectivo'.")
    r = calc_efectos_inversion(data)

    df = pd.DataFrame({
        "Año": [str(a) for a in data["anios"]],
        "FNE (USD)": [round(v) for v in r["fne"][1:]],
        "Factor de descuento": [round(v, 4) for v in r["factor_descuento"]],
        "Valor Actual del FNE": [round(v) for v in r["va_fne"]],
    })
    st.dataframe(df, width="stretch", hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Suma de Valores Actuales", f"${r['suma_va']:,.0f}")
    c2.metric("VAN", f"${r['van']:,.0f}")
    c3.metric("B/C", f"{r['bc']:.3f}")

    if r["bc"] > 1:
        st.success(f"✅ B/C > 1: por cada USD 1 invertido, el proyecto genera USD {r['bc']:.2f} de beneficio (VA).")
    else:
        st.error("⚠️ B/C < 1: a esta TMAR, el proyecto no cubre la inversión en valor actual.")

    fig = go.Figure()
    fig.add_bar(x=["Inversión Inicial"], y=[data["inversion_inicial"]], name="Inversión", marker_color="#D9534F")
    fig.add_bar(x=["Beneficios Actualizados"], y=[r["suma_va"]], name="Beneficios (VA)", marker_color="#2E9E5B")
    fig.update_layout(title="Inversión vs. Beneficios Actualizados", height=320,
                       margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    st.plotly_chart(fig, width="stretch", key="ei_bc_barras")


def tab_ei_pri():
    st.subheader("📅 Período de Recuperación de la Inversión (PRI)")
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    st.caption("🔗 El Flujo Acumulado y la Inversión Inicial vienen automáticamente de 'Flujo de Efectivo'.")
    r = calc_efectos_inversion(data)

    if r["pri_anios"] is None:
        st.error("El proyecto no recupera la inversión dentro del horizonte evaluado.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("a (años completos negativos)", r["a"])
    c2.metric("Inversión no recuperada", f"${r['inv_no_recuperada']:,.0f}")
    c3.metric("FNE del año de recuperación", f"${r['fne_recuperacion']:,.0f}")

    st.markdown(
        f"**PRI = {r['a']} + ({r['inv_no_recuperada']:,.2f} ÷ {r['fne_recuperacion']:,.2f}) "
        f"= {r['pri_anios']:.4f} años**"
    )
    st.markdown(f"### ➡️ {_pri_texto(r['a'], r['pri_anios'])}")

    horizonte = len(data["anios"])
    if r["pri_anios"] <= horizonte:
        st.success(f"✅ Se recupera dentro del horizonte de {horizonte} años, con un margen de "
                   f"holgura de {horizonte - r['pri_anios']:.2f} años antes de que finalice el período proyectado.")
    else:
        st.warning(f"⚠️ El PRI ({r['pri_anios']:.2f} años) supera el horizonte de evaluación de {horizonte} años.")

    anios_flujo = ["Año 0"] + [str(a) for a in data["anios"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=anios_flujo, y=r["acumulado"], mode="lines+markers",
                              name="Flujo Acumulado", line=dict(color="#1F4E78", width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color="#999999", annotation_text="Punto de equilibrio")
    idx_recuperacion = r["a"] + 1
    fig.add_trace(go.Scatter(x=[anios_flujo[idx_recuperacion]], y=[r["acumulado"][idx_recuperacion]],
                              mode="markers", marker=dict(size=14, color="#2E9E5B", symbol="star"),
                              name="Año de recuperación"))
    fig.update_layout(title="Flujo Acumulado y Punto de Recuperación", height=380,
                       margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch", key="ei_pri_grafico")


def _sync_ei_widget_state(data):
    """Antes de dibujar las 5 pestañas, sincroniza cualquier valor ya editado en los
    widgets (aunque su pestaña se dibuje más adelante) para que 'Resumen Ejecutivo'
    -que se dibuja primero- nunca quede un paso atrás."""
    if "ei_tmar" in st.session_state:
        data["tmar"] = st.session_state["ei_tmar"]
    if "ei_inversion_inicial_fe" in st.session_state:
        data["inversion_inicial"] = st.session_state["ei_inversion_inicial_fe"]
    for i in range(len(data["anios"])):
        k_ing = f"ei_ingreso_{i}"
        if k_ing in st.session_state:
            data["ingresos"][i] = st.session_state[k_ing]
        k_ah = f"ei_ahorro_{i}"
        if k_ah in st.session_state:
            data["ahorro_pct"][i] = st.session_state[k_ah]
    for key, campo in [("ei_ratio_costo", "ratio_costo_ventas"), ("ei_gasto_admin_base", "gasto_admin_base"),
                       ("ei_inflacion_admin", "inflacion_admin"), ("ei_deprec_er", "depreciacion_anual"),
                       ("ei_gfin_er", "gastos_financieros_anual"), ("ei_ptu", "ptu_pct"), ("ei_ir", "ir_pct")]:
        if key in st.session_state:
            data[campo] = st.session_state[key]
    st.session_state["efectos_inversion"] = data


def tab_efectos_inversion():
    st.header("💵 Efectos de la Inversión")
    st.caption(
        "Módulo financiero con 5 pestañas interconectadas: cualquier cambio en Ingresos, Costos, "
        "Gastos, TMAR o Inversión Inicial se refleja automáticamente en todas las tablas, gráficos "
        "e indicadores que dependen de él."
    )
    data = init_state("efectos_inversion", lambda: load_json("efectos_inversion"))
    _sync_ei_widget_state(data)
    tabs = st.tabs([
        "📊 Resumen Ejecutivo", "📈 Estado de Resultados Proforma", "💰 Flujo de Efectivo",
        "📉 Relación B/C", "📅 Período de Recuperación (PRI)",
    ], key="tabs_efectos_inversion")
    with tabs[0]:
        with st.container(key="panel_ei_resumen"):
            tab_ei_resumen()
    with tabs[1]:
        with st.container(key="panel_ei_estado_resultados"):
            tab_ei_estado_resultados()
    with tabs[2]:
        with st.container(key="panel_ei_flujo_efectivo"):
            tab_ei_flujo_efectivo()
    with tabs[3]:
        with st.container(key="panel_ei_bc"):
            tab_ei_bc()
    with tabs[4]:
        with st.container(key="panel_ei_pri"):
            tab_ei_pri()


# ====================================================================
# MAIN
# ====================================================================

def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "caratula"

    if st.session_state["page"] == "caratula":
        tab_caratula()
        return

    # ---- Barra lateral de navegación ----
    with st.sidebar:
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=True)
        st.markdown("## 📊 Planificación Estratégica")
        seccion = st.radio(
            "Selecciona el módulo:",
            options=["CULTURA ORGANIZACIONAL", "MATRICES PONDERACIÓN", "MAPA ESTRATÉGICO", "PLANES",
                     "CMI", "EFECTOS DE INVERSIÓN"],
            key="seccion_activa",
        )
        st.divider()
        if st.button("↩️ Volver a la carátula", use_container_width=True):
            st.session_state["page"] = "caratula"
            st.rerun()

    # ---- Módulo de planificación estratégica ----
    st.title("📊 Planificación Estratégica Interactiva")
    st.markdown(
        "Edita cualquier valor de cada pestaña y observa cómo cambian los resultados y su "
        "interpretación en tiempo real."
    )

    # Contenedor con key única por sección: obliga a React a desmontar y
    # volver a montar todo el árbol de DOM al cambiar de módulo, en vez de
    # intentar parchar en el sitio (eso es lo que provocaba el
    # "NotFoundError: Failed to execute 'removeChild'" y dejaba pegado el
    # contenido de la sección anterior debajo del título nuevo).
    with st.container(key=f"contenedor_{seccion}"):
        if seccion == "CULTURA ORGANIZACIONAL":
            tabs = st.tabs([
                "❗ Problemática", "🎯 Misión y Visión", "🏁 Objetivos", "📜 Políticas",
                "💎 Valores", "🧱 Principios", "🗂️ Organigrama",
            ], key="tabs_cultura_organizacional")
            with tabs[0]:
                with st.container(key="panel_problematica"):
                    tab_problematica()
            with tabs[1]:
                with st.container(key="panel_mision_vision"):
                    tab_mision_vision()
            with tabs[2]:
                with st.container(key="panel_objetivos"):
                    tab_objetivos()
            with tabs[3]:
                with st.container(key="panel_politicas"):
                    tab_politicas()
            with tabs[4]:
                with st.container(key="panel_valores"):
                    tab_valores()
            with tabs[5]:
                with st.container(key="panel_principios"):
                    tab_principios()
            with tabs[6]:
                with st.container(key="panel_organigrama"):
                    tab_organigrama()

        elif seccion == "MATRICES PONDERACIÓN":
            tabs = st.tabs([
                "🔗 Holmes / MICMAC", "🏭 EFI", "🌍 EFE", "⛓️ Cadena de Valor",
                "🏆 Perfil Competitivo", "📈 Ansoff", "⚠️ Riesgos", "🔢 FODA Numérico",
            ], key="tabs_matrices_ponderacion")
            with tabs[0]:
                with st.container(key="panel_holmes"):
                    tab_holmes()
            with tabs[1]:
                with st.container(key="panel_efi"):
                    tab_efi()
            with tabs[2]:
                with st.container(key="panel_efe"):
                    tab_efe()
            with tabs[3]:
                with st.container(key="panel_cadena_valor"):
                    tab_cadena_valor()
            with tabs[4]:
                with st.container(key="panel_mpc"):
                    tab_mpc()
            with tabs[5]:
                with st.container(key="panel_ansoff"):
                    tab_ansoff()
            with tabs[6]:
                with st.container(key="panel_riesgos"):
                    tab_riesgos()
            with tabs[7]:
                with st.container(key="panel_foda_numerico"):
                    tab_foda_numerico()

        elif seccion == "MAPA ESTRATÉGICO":
            tab_mapa_estrategico()

        elif seccion == "PLANES":
            tab_planes()

        elif seccion == "EFECTOS DE INVERSIÓN":
            with st.container(key="panel_efectos_inversion"):
                tab_efectos_inversion()

        else:  # CMI
            tab_cmi()


if __name__ == "__main__":
    main()
