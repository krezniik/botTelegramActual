import os
import requests
from flask import Flask, request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

#librerias para trazabilidad
import json
import datetime
from collections import defaultdict


app = Flask(__name__)

TOKEN_TELEGRAM = os.getenv("BOT_TOKEN")
if not TOKEN_TELEGRAM:
    raise ValueError("La variable de entorno BOT_TOKEN no está definida")


API_URL = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}"
estados_usuarios = {}

@app.route("/")
def index():
    return "Bot de tránsito activo 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    print(update)

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        texto = message.get("text", "").strip()
        estado = estados_usuarios.get(chat_id)

        if texto == "/menu":
            mostrar_menu(chat_id)
        
        if estado:
            if estado["paso"] == "fin_llenado":
                estado["registros_pendientes"][estado["registro_activo"]]["hora_fin_llenado"] = texto
                estado["paso"] = "inicio_proceso"
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "⏱️ Ingresa la hora de inicio de proceso (ej. 10:10):"
                })

            elif estado["paso"] == "inicio_proceso":
                estado["registros_pendientes"][estado["registro_activo"]]["hora_inicio_proceso"] = texto
                estado["paso"] = "fin_proceso"
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "⏱️ Ingresa la hora de fin de proceso (ej. 11:45):"
                })

            elif estado["paso"] == "fin_proceso":
                estado["registros_pendientes"][estado["registro_activo"]]["hora_fin_proceso"] = texto
                registro = estado["registros_pendientes"].pop(estado["registro_activo"])
                estado.pop("registro_activo")
                estado["paso"] = None

                texto = (
                    "✅ Registro completado:\n"
                    f"🧯 Autoclave: {registro['autoclave']}\n"
                    f"🧺 Medida: {registro['medida']}\n"
                    f"📆 Día Juliano: {registro['juliano']}\n"
                    f"⏱️ Inicio llenado: {registro['hora_inicio_llenado']}\n"
                    f"⏱️ Fin llenado: {registro['hora_fin_llenado']}\n"
                    f"🔥 Inicio proceso: {registro['hora_inicio_proceso']}\n"
                    f"✅ Fin proceso: {registro['hora_fin_proceso']}"
                )

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": texto
                })



        elif estado and estado["paso"] == "traza_medida":
            medida = texto
            estados_usuarios[chat_id]["trazabilidad"]["medida"] = medida
            estados_usuarios[chat_id]["paso"] = "traza_autoclave"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Medida: {medida}\n\n🚪 ¿Qué número de autoclave estás usando?"
            })

        elif estado and estado["paso"] == "traza_autoclave":
            autoclave = texto
            estados_usuarios[chat_id]["trazabilidad"]["autoclave"] = autoclave
            estados_usuarios[chat_id]["paso"] = "traza_dia"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Autoclave: {autoclave}\n\n📆 ¿Cuál es el día juliano?"
            })

        elif estado and estado["paso"] == "traza_dia":
            dia_juliano = texto
            estados_usuarios[chat_id]["trazabilidad"]["dia_juliano"] = dia_juliano
            estados_usuarios[chat_id]["paso"] = "traza_hora_inicio"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Día juliano: {dia_juliano}\n\n⏰ ¿Hora de inicio de llenado? (formato HH:MM)"
            })

        elif estado and estado["paso"] == "traza_hora_inicio":
            hora_inicio = texto
            estados_usuarios[chat_id]["trazabilidad"]["hora_inicio_llenado"] = hora_inicio
            estados_usuarios[chat_id]["paso"] = "traza_espera_llenado"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Hora de inicio: {hora_inicio}\n\n⏳ Esperando que finalice el llenado...\n\nCuando finalice, escribe la hora de fin de llenado (HH:MM)"
            })

        elif estado and estado["paso"] == "traza_espera_llenado":
            hora_fin_llenado = texto
            estados_usuarios[chat_id]["trazabilidad"]["hora_fin_llenado"] = hora_fin_llenado
            estados_usuarios[chat_id]["paso"] = "traza_inicio_proceso"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Fin de llenado: {hora_fin_llenado}\n\n⏰ ¿Hora de inicio de proceso? (HH:MM)"
            })

        elif estado and estado["paso"] == "traza_inicio_proceso":
            hora_inicio_proceso = texto
            estados_usuarios[chat_id]["trazabilidad"]["hora_inicio_proceso"] = hora_inicio_proceso
            estados_usuarios[chat_id]["paso"] = "traza_fin_proceso"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"✅ Inicio de proceso: {hora_inicio_proceso}\n\n⏰ ¿Hora de fin de proceso? (HH:MM)"
            })

        elif estado and estado["paso"] == "traza_fin_proceso":
            hora_fin_proceso = texto
            estado["trazabilidad"]["hora_fin_proceso"] = hora_fin_proceso

            datos = estado["trazabilidad"]
            medida = datos["medida"]
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_archivo = f"trazabilidad_{fecha}.json"

        elif estado and estado["paso"] == "juliano":
            estado["juliano"] = texto
            estado["paso"] = "inicio_llenado"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "⏱️ Ingresa la hora de inicio de llenado (formato 24h, ej: 13:15):"
            })

        elif estado and estado["paso"] == "inicio_llenado":
            estado["inicio_llenado"] = texto

            # Construimos el registro en espera
            nuevo_registro = {
                "autoclave": estado.get("autoclave"),
                "producto": estado.get("producto"),
                "medida": estado.get("medida"),
                "juliano": estado.get("juliano"),
                "inicio_llenado": estado.get("inicio_llenado"),
                "fin_llenado": None,
                "inicio_proceso": None,
                "fin_proceso": None
            }

            if "registros_pendientes" not in estado:
                estado["registros_pendientes"] = []

            estado["registros_pendientes"].append(nuevo_registro)

            # Limpiar paso actual
            estado["paso"] = None

            teclado = {
                "inline_keyboard": [
                    [{"text": "➕ Añadir otro registro", "callback_data": "nuevo_registro_traza"}],
                    [{"text": "📲 Completar un registro pendiente", "callback_data": "completar_registro"}],
                    [{"text": "⬅️ Volver al menú principal", "callback_data": "volver_menu"}]
                ]
            }

            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "📋 Registro parcial guardado (en espera de continuar llenado y proceso).\n\n¿Qué deseas hacer ahora?",
                "reply_markup": teclado
            })






            # Cargar registros existentes
            try:
                with open(nombre_archivo, "r") as f:
                    registros = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                registros = {}

            # Agregar a la hoja correspondiente
            if medida not in registros:
                registros[medida] = []
            registros[medida].append(datos)

            with open(nombre_archivo, "w") as f:
                json.dump(registros, f, indent=2)

            resumen = (
                f"✅ Registro completado para *{medida}*\n\n"
                f"Autoclave: {datos['autoclave']}\n"
                f"Día juliano: {datos['dia_juliano']}\n"
                f"🕒 Inicio llenado: {datos['hora_inicio_llenado']}\n"
                f"🕒 Fin llenado: {datos['hora_fin_llenado']}\n"
                f"🕒 Inicio proceso: {datos['hora_inicio_proceso']}\n"
                f"🕒 Fin proceso: {datos['hora_fin_proceso']}\n"
            )

            teclado = {
                "inline_keyboard": [
                    [{"text": "➕ Nuevo registro", "callback_data": "traza_nuevo"}],
                    [{"text": "↩️ Menú principal", "callback_data": "volver_menu"}]
                ]
            }

            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": resumen,
                "parse_mode": "Markdown",
                "reply_markup": teclado
            })

            estados_usuarios.pop(chat_id)

        elif estado and estado["paso"] == "autoclave":
            estado["registro_parcial"]["autoclave"] = texto
            estado["paso"] = "producto_trazabilidad"

            teclado = {
                "inline_keyboard": [
                    [{"text": "FND", "callback_data": "producto_traza_FND"},
                     {"text": "FRD", "callback_data": "producto_traza_FRD"}],
                    [{"text": "FNE", "callback_data": "producto_traza_FNE"},
                     {"text": "FRE", "callback_data": "producto_traza_FRE"}]
                ]
            }

            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "🍲 Selecciona el tipo de producto:",
                "reply_markup": teclado
            })




        elif estado and estado["paso"] == "cantidad":
            try:
                cantidad = int(texto)
                estado["canastas"] = cantidad
                llenadora = estado.get("llenadora")

                if llenadora == "Chub":
                    estado["pin"] = "único"
                    estado["paso"] = "otro_lote"
                elif llenadora == "M3":
                    estado["pin"] = "grande"
                    estado["paso"] = "otro_lote"
                else:
                    estado["paso"] = "pin"

                if estado["paso"] == "pin":
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "🔩 Pin Pequeño", "callback_data": "pin_pequeño"},
                             {"text": "🔩 Pin Grande", "callback_data": "pin_grande"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Canastas: {cantidad}\n\n🔧 Selecciona el tamaño del pin:",
                        "reply_markup": teclado
                    })
                else:
                    pin_texto = estado["pin"]
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "✅ Sí", "callback_data": "otro_si"},
                             {"text": "❌ No", "callback_data": "otro_no"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Canastas: {cantidad}\n\nPin asignado automáticamente: {pin_texto} 🔩\n\n➕ ¿Deseas agregar otro lote?",
                        "reply_markup": teclado
                    })

            except ValueError:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❗ Ingresa un número válido de canastas."
                })

    elif "callback_query" in update:
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        callback_data = update["callback_query"]["data"]
        if callback_data == "menu_tiempos":
            mostrar_menu_tiempos(chat_id)

        elif callback_data.startswith("tiempo_"):
            medida = callback_data.split("tiempo_")[1]
            mostrar_proceso_termico(chat_id, medida)
        
        elif callback_data == "trazabilidad":
            mostrar_opciones_trazabilidad(chat_id)

        elif callback_data == "nuevo_trazabilidad":
            estados_usuarios[chat_id] = {"paso": "inicio_traza"}
            enviar_mensaje(chat_id, "Has iniciado un nuevo registro de trazabilidad.")

        elif estado and estado.get("paso") == "medida_traza":
            enviar_mensaje(chat_id, "Recibida medida para trazabilidad. Aún no hay lógica completa.")
            
        elif callback_data == "traza_nuevo":
            estados_usuarios[chat_id] = {
                "paso": "traza_medida",
                "trazabilidad": {}
            }
            medidas = ["4 oz", "8 oz", "14 oz", "16 oz", "28 oz", "35 oz", "40 oz", "80 oz"]
            teclado_medidas = {
                "inline_keyboard": [
                    [{"text": medida, "callback_data": f"traza_medida_{medida}"} for medida in medidas[i:i+2]]
                    for i in range(0, len(medidas), 2)
                ]
            }
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "📏 ¿Qué medida estás trabajando?",
                "reply_markup": teclado_medidas
            })


        elif callback_data == "traza_hojas":
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_archivo = f"trazabilidad_{fecha}.json"

            try:
                with open(nombre_archivo, "r") as f:
                    registros = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                registros = {}

            if not registros:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❌ No hay registros guardados para hoy."
                })
            else:
                teclado = {
                    "inline_keyboard": [
                        [{"text": hoja, "callback_data": f"hoja_{hoja}"}] for hoja in registros.keys()
                    ]
                }
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "📄 Selecciona la hoja que deseas ver:",
                    "reply_markup": teclado
                })


        elif callback_data.startswith("hoja_"):
            hoja = callback_data.split("_", 1)[1]
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_archivo = f"trazabilidad_{fecha}.json"

            try:
                with open(nombre_archivo, "r") as f:
                    registros = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                registros = {}

            lotes = registros.get(hoja, [])

            if not lotes:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"❌ No hay lotes registrados para {hoja}."
                })
            else:
                texto = f"📄 *Hoja: {hoja}*\n\n"
                for i, lote in enumerate(lotes, 1):
                    texto += (
                        f"*Lote {i}*\n"
                        f"Autoclave: {lote['autoclave']}\n"
                        f"Producto: {lote['producto']}\n"
                        f"Día juliano: {lote['dia_juliano']}\n"
                        f"Inicio llenado: {lote['inicio_llenado']}\n"
                        f"Fin llenado: {lote.get('fin_llenado', '⏳')}\n"
                        f"Inicio proceso: {lote.get('inicio_proceso', '⏳')}\n"
                        f"Fin proceso: {lote.get('fin_proceso', '⏳')}\n\n"
                    )

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": texto,
                    "parse_mode": "Markdown"
                })

        elif callback_data == "nuevo_trazabilidad":
            estados_usuarios[chat_id] = {
                "paso": "seleccion_hoja",
                "registro_parcial": {}
            }

            medidas = [
                "4 oz", "5.5 oz", "8 oz", "8 oz Entero", "8 oz Picante",
                "14 oz", "14 oz Arreglado", "14.1 Entero", "14.1 oz Picante",
                "16 oz", "28 oz", "28 oz Entero", "35 oz", "40 oz", "4lbs Chub", "80 oz"
            ]

            teclado = {
                "inline_keyboard": [
                    [
                        {"text": medidas[i], "callback_data": f"hoja_nueva_{medidas[i]}"},
                        {"text": medidas[i+1], "callback_data": f"hoja_nueva_{medidas[i+1]}"}
                    ] for i in range(0, len(medidas) - 1, 2)
                ]
            }

            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Selecciona la hoja (medida/tipo) para registrar:",
                "reply_markup": teclado
            })

        elif callback_data.startswith("hoja_nueva_"):
            hoja = callback_data.split("_", 2)[2]
            estado = estados_usuarios.get(chat_id)
            if estado and estado["paso"] == "seleccion_hoja":
                estado["registro_parcial"]["hoja"] = hoja
                estado["paso"] = "autoclave"

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Hoja seleccionada: {hoja}\n\n🔢 ¿Número de autoclave?"
                })


        elif callback_data.startswith("producto_traza_"):
            producto = callback_data.split("_", 2)[2]
            estado = estados_usuarios.get(chat_id)
            if estado and estado["paso"] == "producto_trazabilidad":
                estado["registro_parcial"]["producto"] = producto
                estado["paso"] = "medida_trazabilidad"

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "📏 Ingresa la medida exacta (por ejemplo: 14 oz o 28 oz Entero):"
                })

        elif estado["paso"] == "medida_traza":
            estado["medida"] = callback_data.split("medida_")[1]
            estado["paso"] = "juliano"
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "📅 Ingresa el día juliano:"
            })

        elif callback_data == "completar_registro":
            pendientes = estado.get("registros_pendientes", [])
            if not pendientes:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "📭 No hay registros pendientes por completar."
                })
            else:
                botones = []
                for idx, r in enumerate(pendientes):
                    texto = f"{r['autoclave']} | {r['medida']} | {r['juliano']}"
                    botones.append([{
                        "text": texto,
                        "callback_data": f"pendiente_{idx}"
                    }])

                teclado = {"inline_keyboard": botones}
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "Selecciona el registro que deseas completar:",
                    "reply_markup": teclado
                })


        elif callback_data.startswith("pendiente_"):
            idx = int(callback_data.split("_")[1])
            pendientes = estado.get("registros_pendientes", [])
            if idx < len(pendientes):
                estado["registro_activo"] = idx
                estado["paso"] = "fin_llenado"
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "⏱️ Ingresa la hora de fin de llenado (ej. 09:45):"
                })

        elif callback_data == "ver_registros_hoja":
            archivos = [
                f for f in os.listdir(".")
                if f.endswith(".json") and datetime.now().strftime("%Y-%m-%d") in f
            ]

            if not archivos:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❌ No se encontraron hojas activas para hoy."
                })
            else:
                teclado = {
                    "inline_keyboard": [
                        [{"text": f"📄 {archivo}", "callback_data": f"ver_hoja_{archivo}"}]
                        for archivo in archivos
                    ]
                }
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "📂 Hojas disponibles hoy:",
                    "reply_markup": teclado
                })

        elif callback_data.startswith("ver_hoja_"):
            nombre_archivo = callback_data.split("ver_hoja_")[1]

            if os.path.exists(nombre_archivo):
                with open(nombre_archivo, "r") as f:
                    registros = json.load(f)

                if not registros:
                    texto = f"📄 *{nombre_archivo}*\n\n(No hay registros aún)"
                else:
                    texto = f"📄 *{nombre_archivo}*\n\n"
                    for i, r in enumerate(registros, 1):
                        texto += (
                            f"*Lote {i}*\n"
                            f"⚙️ Autoclave: {r.get('autoclave', 'N/A')}\n"
                            f"🫘 Producto: {r.get('producto', 'N/A')}\n"
                            f"📏 Medida: {r.get('medida', 'N/A')}\n"
                            f"📅 Día juliano: {r.get('dia_juliano', 'N/A')}\n"
                            f"🕒 Inicio llenado: {r.get('hora_inicio_llenado', 'N/A')}\n"
                            f"🕒 Fin llenado: {r.get('hora_fin_llenado', 'N/A')}\n"
                            f"🕒 Inicio proceso: {r.get('hora_inicio_proceso', 'N/A')}\n"
                            f"🕒 Fin proceso: {r.get('hora_fin_proceso', 'N/A')}\n\n"
                        )

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": texto,
                    "parse_mode": "Markdown"
                })
            else:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❌ No se pudo encontrar la hoja seleccionada."
                })

        elif callback_data.startswith("ver_hoja_"):
            nombre_archivo = callback_data.split("ver_hoja_")[1]

            if os.path.exists(nombre_archivo):
                with open(nombre_archivo, "r") as f:
                    registros = json.load(f)

                if not registros:
                    texto = f"📄 *{nombre_archivo}*\n\n(No hay registros aún)"
                else:
                    texto = f"📄 *{nombre_archivo}*\n\n"
                    for i, r in enumerate(registros, 1):
                        texto += (
                            f"*Lote {i}*\n"
                            f"⚙️ Autoclave: {r.get('autoclave', 'N/A')}\n"
                            f"🫘 Producto: {r.get('producto', 'N/A')}\n"
                            f"📏 Medida: {r.get('medida', 'N/A')}\n"
                            f"📅 Día juliano: {r.get('dia_juliano', 'N/A')}\n"
                            f"🕒 Inicio llenado: {r.get('hora_inicio_llenado', 'N/A')}\n"
                            f"🕒 Fin llenado: {r.get('hora_fin_llenado', 'N/A')}\n"
                            f"🕒 Inicio proceso: {r.get('hora_inicio_proceso', 'N/A')}\n"
                            f"🕒 Fin proceso: {r.get('hora_fin_proceso', 'N/A')}\n\n"
                        )

                teclado = {
                    "inline_keyboard": [
                        [{"text": "↩️ Volver al menú principal", "callback_data": "volver_menu"}]
                    ]
                }

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": texto,
                    "parse_mode": "Markdown",
                    "reply_markup": teclado
                })
            else:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❌ No se pudo encontrar la hoja seleccionada."
                })



        elif callback_data == "volver_menu":
            mostrar_menu(chat_id)

        elif callback_data == "reiniciar_tiempos":
            mostrar_menu_tiempos(chat_id)

        estado = estados_usuarios.get(chat_id)

        if callback_data == "transito":
            estados_usuarios[chat_id] = {
                "paso": "llenadora",
                "reportes": []
            }
            mostrar_llenadoras(chat_id)

        elif callback_data.startswith("llenadora_"):
            llenadora = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "llenadora":
                estado["llenadora"] = llenadora

                if llenadora == "Chub":
                    estado["medida"] = "4lbs"
                    estado["paso"] = "producto"
                    productos = [
                        {"text": "FNE", "callback_data": "producto_FNE"},
                        {"text": "FRE", "callback_data": "producto_FRE"}
                    ]
                    teclado = {"inline_keyboard": [[p] for p in productos]}
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "🍲 Selecciona el tipo de producto:",
                        "reply_markup": teclado
                    })
                else:
                    estado["paso"] = "medida"
                    medidas = ["4oz", "8oz", "14oz", "16oz", "28oz", "35oz", "40oz", "80oz"]
                    teclado_medidas = {
                        "inline_keyboard": [
                            [{"text": medida, "callback_data": f"medida_{medida}"} for medida in medidas[i:i+2]]
                            for i in range(0, len(medidas), 2)
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Llenadora: {llenadora}\n\n📏 ¿Qué medida estás trabajando?",
                        "reply_markup": teclado_medidas
                    })

        elif callback_data.startswith("medida_"):
            medida = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "medida":
                estado["medida"] = medida
                estado["paso"] = "producto"
                llenadora = estado.get("llenadora")

                productos = [
                    {"text": "FND", "callback_data": "producto_FND"},
                    {"text": "FRD", "callback_data": "producto_FRD"},
                    {"text": "FRS", "callback_data": "producto_FRD Seda"},
                    {"text": "FNA", "callback_data": "producto_FND Arreglados"},
                    {"text": "FNP", "callback_data": "producto_FND Picante medio"},
                    {"text": "FRP", "callback_data": "producto_FRD Picante medio"}
                ]

                if llenadora in ["M1", "Chub"]:
                    productos.append({"text": "FNE", "callback_data": "producto_FND Entero"})
                    productos.append({"text": "FRE", "callback_data": "producto_FRD Entero"})

                teclado_productos = {
                    "inline_keyboard": [productos[i:i+2] for i in range(0, len(productos), 2)]
                }

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Medida: {medida}\n\n🍲 Selecciona el tipo de producto:",
                    "reply_markup": teclado_productos
                })

        elif callback_data.startswith("producto_"):
            producto = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "producto":
                estado["producto"] = producto
                llenadora = estado.get("llenadora")

                if llenadora == "Chub":
                    estado["mercado"] = "RTCA"
                    estado["paso"] = "cantidad"
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Producto: {producto}\n🌎 Mercado asignado automáticamente: RTCA\n\n🔢 ¿Cuántas canastas se reportaron?"
                    })
                else:
                    estado["paso"] = "mercado"
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "RTCA 🇬🇹", "callback_data": "mercado_RTCA"},
                             {"text": "FDA 🇺🇸", "callback_data": "mercado_FDA"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Producto: {producto}\n\n🌎 Selecciona el mercado:",
                        "reply_markup": teclado
                    })

        elif callback_data.startswith("mercado_"):
            mercado = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "mercado":
                estado["mercado"] = mercado
                estado["paso"] = "cantidad"
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Mercado: {mercado}\n\n🔢 ¿Cuántas canastas se reportaron?"
                })

        elif callback_data.startswith("pin_"):
            pin = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "pin":
                estado["pin"] = pin
                estado["paso"] = "otro_lote"
                teclado = {
                    "inline_keyboard": [
                        [{"text": "✅ Sí", "callback_data": "otro_si"},
                         {"text": "❌ No", "callback_data": "otro_no"}]
                    ]
                }
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Pin: {pin}\n\n➕ ¿Deseas agregar otro lote?",
                    "reply_markup": teclado
                })

        elif callback_data.startswith("otro_"):
            if estado:
                cajas_por_canasta = {
                    "4oz": {"grande": 0, "pequeño": 110},
                    "8oz": {"grande": 68, "pequeño": 93.5},
                    "14oz": {"grande": 80, "pequeño": 110},
                    "16oz": {"grande": 0, "pequeño": 165},
                    "28oz": {"grande": 58, "pequeño": 0},
                    "35oz": {"grande": 53, "pequeño": 0},
                    "40oz": {"grande": 48, "pequeño": 0},
                    "80oz": {"grande": 53, "pequeño": 0},
                    "4lbs": {"único": 81}
                }

                estado["reportes"].append({
                    "llenadora": estado["llenadora"],
                    "medida": estado["medida"],
                    "producto": estado["producto"],
                    "mercado": estado["mercado"],
                    "canastas": estado["canastas"],
                    "pin": estado["pin"]
                })

                if callback_data == "otro_si":
                    estado["paso"] = "llenadora"
                    mostrar_llenadoras(chat_id)
                else:
                    texto = "✅ *Resumen del turno:*\n"
                    for idx, r in enumerate(estado["reportes"], 1):
                        medida = r["medida"]
                        pin = r["pin"]
                        canastas = int(r["canastas"])
                        cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                        cajas = canastas * cajas_por_pin
                        texto += (
                            f"\n*Lote {idx}*\n"
                            f"⚙️ Llenadora: {r['llenadora']}\n"
                            f"📏 Medida: {medida}\n"
                            f"🍲 Producto: {r['producto']}\n"
                            f"🌎 Mercado: {r['mercado']}\n"
                            f"🧺 Canastas: {canastas} | 🔩 Pin: {pin}\n"
                            f"📦 Cajas: {cajas} (≈ {cajas_por_pin} x canasta)"
                        )

                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": texto,
                        "parse_mode": "Markdown"
                    })


            #   AQUI COMIENZA ÚLTIMO CAMBIO REALIZADO
            
                    from collections import defaultdict
                    agrupado = defaultdict(list)
                    for r in estado["reportes"]:
                        agrupado[r["llenadora"]].append(r)

                    resumen_elegante = "*Tránsito 📋*\n"
                    for llenadora, lotes in agrupado.items():
                        resumen_elegante += f"\n⚙️ *{llenadora}*"
                        total_cajas_llenadora = 0
                        for r in lotes:
                            producto = r["producto"]
                            medida = r["medida"]
                            mercado = r["mercado"]
                            canastas = int(r["canastas"])
                            pin = r["pin"]
                            cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                            total_cajas = int(canastas * cajas_por_pin)
                            total_cajas_llenadora += total_cajas

                            bandera = "🇬🇹" if mercado == "RTCA" else "🇺🇸"
                            
                            resumen_elegante += (
                                f"\n{producto + " 🫘"} {medida} {mercado} {bandera}\n*{total_cajas:,} cajas* 📦\n"
                            )
                        if len(lotes) > 1:
                            resumen_elegante += f"\n*Total: {total_cajas_llenadora:,} cajas* 📦\n"

                    # Guardar resumen elegante en estado
                    estado["resumen_final"] = resumen_elegante

                    # Preguntar si se desea enviar al grupo
                    teclado_confirmacion = {
                        "inline_keyboard": [
                            [{"text": "📤 Enviar al grupo", "callback_data": "enviar_grupo"},
                             {"text": "❌ No enviar", "callback_data": "no_enviar"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": resumen_elegante + "\n¿Deseas enviar este resumen al grupo?",
                        "parse_mode": "Markdown",
                        "reply_markup": teclado_confirmacion
                    })
                    
        elif callback_data == "enviar_grupo":
            resumen_final = estado.get("resumen_final")
            if resumen_final:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": -1002710248563,
                    "text": resumen_final,
                    "parse_mode": "Markdown"
                })
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "✅ Resumen enviado al grupo."
            })
            estados_usuarios.pop(chat_id)

        elif callback_data == "no_enviar":
            requests.post(f"{API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "✅ Resumen guardado, no se enviará al grupo."
            })
            estados_usuarios.pop(chat_id)
        #   AQUI TERMINA ULTIMO CAMBIO REALIZADO.
        
                    # Crear y enviar resumen simple al grupo
                    #resumen_simple = "*Tránsito 📋*"
                    #for r in estado["reportes"]:
                        #producto = r["producto"]
                        #medida = r["medida"]
                        #mercado = r["mercado"]
                        #canastas = int(r["canastas"])
                        #pin = r["pin"]
                        #cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                        #total_cajas = int(canastas * cajas_por_pin)

                        #bandera = "🇬🇹" if mercado == "RTCA" else "🇺🇸"

                        #resumen_simple += f"\n\n{producto + " 🫘"} \n{medida} {mercado} {bandera}\n*{total_cajas:,} cajas* 📦"

                    # Enviar al grupo de Telegram
                    #requests.post(f"{API_URL}/sendMessage", json={
                        #"chat_id": -1002710248563,
                        #"text": resumen_simple,
                        #"parse_mode": "Markdown"
                    #})
                    
                    #estados_usuarios.pop(chat_id)

    return '', 200

def mostrar_menu(chat_id):
    keyboard = [
        [InlineKeyboardButton("📦 Reportar Tránsito", callback_data="menu_transito")],
        [InlineKeyboardButton("🕒 Ver Tiempos", callback_data="menu_tiempos")],
        [InlineKeyboardButton("📋 Trazabilidad", callback_data="trazabilidad")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Selecciona una herramienta:",
        "reply_markup": markup.to_dict()
    })


def mostrar_llenadoras(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "⚙️ M1", "callback_data": "llenadora_M1"},
             {"text": "⚙️ M2", "callback_data": "llenadora_M2"}],
            [{"text": "⚙️ M3", "callback_data": "llenadora_M3"},
             {"text": "⚙️ Chub", "callback_data": "llenadora_Chub"}]
        ]
    }
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Selecciona la llenadora:",
        "reply_markup": teclado
    })

def mostrar_menu_tiempos(chat_id):
    medidas = [
        "4 oz", "5.5 oz", "8 oz", "8 oz Entero", "8 oz Picante",
        "14 oz", "14 oz Arreglado", "14.1 Entero", "14.1 oz Picante",
        "16 oz", "28 oz", "28 oz Entero", "35 oz", "40 oz", "4lbs Chub", "80 oz"
    ]

    teclado = {
        "inline_keyboard": [
            [
                {"text": medidas[i].replace("_", " "), "callback_data": f"tiempo_{medidas[i]}"},
                {"text": medidas[i+1].replace("_", " "), "callback_data": f"tiempo_{medidas[i+1]}"}
            ]
            for i in range(0, len(medidas) - 1, 2)
        ] + (
            [[{"text": medidas[-1].replace("_", " "), "callback_data": f"tiempo_{medidas[-1]}"}]]
            if len(medidas) % 2 == 1 else []
        )
    }

    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Selecciona la medida y tipo:",
        "reply_markup": teclado
    })


def mostrar_proceso_termico(chat_id, medida):
    procesos = {
        "80 oz": {
            "pasos": [
                (1, 90.0, 1.800, 6),
                (2, 122.5, 2.400, 21),
                (3, 122.5, 2.400, 5),
                (4, 122.5, 2.400, 99),
                (5, 122.5, 2.400, 37),
                (6, 80.0, 2.400, 5),
                (7, 40.0, 0.400, 20),
                (8, 28.0, 0.100, 65),
            ]
        }
        # Aquí irán los demás procesos...
    }

    if medida not in procesos:
        requests.post(f"{API_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": "❌ Proceso no disponible aún."
        })
        return

    pasos = procesos[medida]["pasos"]
    total_min = sum(p[3] for p in pasos)
    horas = total_min // 60
    minutos = total_min % 60

    texto = f"🧪 Proceso térmico para {medida.replace('_', ' ')}\n\n"
    texto += "PASO | °C | Bar | Min\n"
    texto += "----------------------------------------------\n"
    for paso in pasos:
        texto += f" {paso[0]:<4}|  {paso[1]:<7} |    {paso[2]:<8}  |   {paso[3]}\n"
    texto += f"\n⏱️ Tiempo total estimado: {total_min} minutos (~{horas}h {minutos}min)"

    teclado = {
        "inline_keyboard": [
            [{"text": "🔄 Reiniciar herramienta", "callback_data": "reiniciar_tiempos"}],
            [{"text": "↩️ Volver al menú principal", "callback_data": "volver_menu"}]
        ]
    }

    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": texto,
        "reply_markup": teclado
    })

#INICIO DE FUNCIÓN "TRAZABILIDAD"

from datetime import datetime
import os

def mostrar_opciones_trazabilidad(chat_id):
    hoy = datetime.now().strftime("%Y-%m-%d")
    archivos_existentes = []
    if os.path.exists("trazabilidad"):
        archivos_existentes = [
            archivo for archivo in os.listdir("trazabilidad")
            if archivo.startswith(hoy)

       ]

    botones = [[{"text": "➕ Nuevo Registro", "callback_data": "nuevo_trazabilidad"}]]

    if archivos_existentes:
        botones.append([{"text": "📂 Continuar registro existente", "callback_data": "continuar_trazabilidad"}])

    teclado = {"inline_keyboard": botones}

    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "📄 *Trazabilidad de autoclaves*\n\n¿Qué deseas hacer?",
        "parse_mode": "Markdown",
        "reply_markup": teclado

    })
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
