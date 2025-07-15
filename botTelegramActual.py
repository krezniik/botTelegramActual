import time
import requests

TOKEN_TELEGRAM = "8015050577:AAGvyeTpcefEL_vifoJb_KnesyHepW5Sa38"
API_URL = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}"
last_update_id = None
estados_usuarios = {}

def mostrar_menu(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "📦 Reportar tránsito", "callback_data": "transito"}]
        ]
    }
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Menú principal\n\n🛠️ Selecciona una herramienta:",
        "reply_markup": teclado
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

def revisar_mensajes():
    global last_update_id
    while True:
        try:
            res = requests.get(f"{API_URL}/getUpdates", params={"offset": last_update_id})
            data = res.json()

            for update in data.get("result", []):
                last_update_id = update["update_id"] + 1

                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    texto = message.get("text", "").strip()
                    estado = estados_usuarios.get(chat_id)

                    if texto == "/menu":
                        mostrar_menu(chat_id)

                    elif estado and estado["paso"] == "cantidad":
                        try:
                            cantidad = int(texto)
                            estado["canastas"] = cantidad
                            llenadora = estado.get("llenadora")

                            if llenadora == "Chub":
                                estado["pin"] = "único"
                                estado["paso"] = "otro_lote"
                                teclado = {
                                    "inline_keyboard": [
                                        [{"text": "✅ Sí", "callback_data": "otro_si"},
                                         {"text": "❌ No", "callback_data": "otro_no"}]
                                    ]
                                }
                                requests.post(f"{API_URL}/sendMessage", json={
                                    "chat_id": chat_id,
                                    "text": f"✅ Canastas: {cantidad}\n\nPin asignado automáticamente: único 🔩\n\n➕ ¿Deseas agregar otro lote?",
                                    "reply_markup": teclado
                                })

                            elif llenadora == "M3":
                                estado["pin"] = "grande"
                                estado["paso"] = "otro_lote"
                                teclado = {
                                    "inline_keyboard": [
                                        [{"text": "✅ Sí", "callback_data": "otro_si"},
                                         {"text": "❌ No", "callback_data": "otro_no"}]
                                    ]
                                }
                                requests.post(f"{API_URL}/sendMessage", json={
                                    "chat_id": chat_id,
                                    "text": f"✅ Canastas: {cantidad}\n\nPin asignado automáticamente: grande 🔩\n\n➕ ¿Deseas agregar otro lote?",
                                    "reply_markup": teclado
                                })

                            else:
                                estado["paso"] = "pin"
                                teclado = {
                                    "inline_keyboard": [
                                        [{"text": "🔩 Pin Pequeño", "callback_data": "pin_pequeno"},
                                         {"text": "🔩 Pin Grande", "callback_data": "pin_grande"}]
                                    ]
                                }
                                requests.post(f"{API_URL}/sendMessage", json={
                                    "chat_id": chat_id,
                                    "text": f"✅ Canastas: {cantidad}\n\n🔧 Selecciona el tamaño del pin:",
                                    "reply_markup": teclado
                                })

                        except ValueError:
                            requests.post(f"{API_URL}/sendMessage", data={
                                "chat_id": chat_id,
                                "text": "❗ Ingresa un número válido de canastas."
                            })

                elif "callback_query" in update:
                    chat_id = update["callback_query"]["message"]["chat"]["id"]
                    callback_data = update["callback_query"]["data"]
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
                            estado["paso"] = "medida"

                            medidas = []
                            if llenadora in ["M1", "M2", "M3"]:
                                medidas = ["4oz", "8oz", "14oz", "16oz"]
                            elif llenadora == "Chub":
                                medidas = ["4lbs"]

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

                            teclado = {
                                "inline_keyboard": [
                                    [{"text": "FND", "callback_data": "producto_FND"},
                                     {"text": "FRD", "callback_data": "producto_FRD"}],
                                    [{"text": "FNE", "callback_data": "producto_FNE"},
                                     {"text": "FRE", "callback_data": "producto_FRE"}]
                                ]
                            }

                            requests.post(f"{API_URL}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": f"✅ Medida: {medida}\n\n🍲 Selecciona el tipo de producto:",
                                "reply_markup": teclado
                            })

                    elif callback_data.startswith("producto_"):
                        producto = callback_data.split("_", 1)[1]
                        if estado and estado["paso"] == "producto":
                            estado["producto"] = producto
                            estado["paso"] = "mercado"

                            teclado = {
                                "inline_keyboard": [
                                    [{"text": "RTCA", "callback_data": "mercado_RTCA"},
                                     {"text": "FDA", "callback_data": "mercado_FDA"}]
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

                            requests.post(f"{API_URL}/sendMessage", data={
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
                                "4oz": {"grande": 17, "pequeno": 25},
                                "8oz": {"grande": 15, "pequeno": 22},
                                "14oz": {"grande": 14, "pequeno": 20},
                                "16oz": {"grande": 12, "pequeno": 18},
                                "28oz": {"grande": 10, "pequeno": 14},
                                "35oz": {"grande": 9, "pequeno": 13},
                                "40oz": {"grande": 8, "pequeno": 12},
                                "80oz": {"grande": 6, "pequeno": 9},
                                "4lbs": {"único": 10}
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

                            elif callback_data == "otro_no":
                                texto = "✅ *Resumen del turno:*\n"
                                for idx, r in enumerate(estado["reportes"], 1):
                                    medida = r["medida"]
                                    pin = r["pin"]
                                    canastas = int(r["canastas"])
                                    cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                                    cajas = canastas * cajas_por_pin

                                    texto += (
                                        f"\n📦 *Lote {idx}*\n"
                                        f"🔹 Llenadora: {r['llenadora']}\n"
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

                                estados_usuarios.pop(chat_id)

        except Exception as e:
            print("❗ Error:", e)
            time.sleep(2)

if __name__ == "__main__":
    revisar_mensajes()