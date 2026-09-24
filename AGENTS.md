# Trabajo en zabbix-laya

- Mantener ejemplos publicados sintéticos. No incorporar hosts reales, alertas privadas, contraseñas, tokens, claves SSH ni credenciales de Zabbix en código, pruebas o documentación.
- Revisar el diff preparado antes de cada commit y push. `.gitignore` no protege de secretos incrustados en archivos versionados.
- Usar la identidad pública `j3udiel` con el correo noreply de GitHub configurado en este repositorio. Comprobar autor y committer para no publicar correos ni nombres de servidores locales.
- Mantener `.venv/`, `.cache/`, `resultados/`, logs y `.env*` fuera del repositorio.
- La interfaz es un laboratorio local, sin acciones sobre Zabbix. No añadir remediación ni acceso a infraestructura real sin petición del usuario.
- La fase autorizada el 2026-09-24 permite al proyecto separado AI Monitoring consultar este motor local y publicar predicciones en su Zabbix LAB. La UI de este repositorio no recibe credenciales ni ejecuta esas escrituras; los detalles privados y la autorización viven en el ADR-013 del orquestador.
- Verificar cambios de la interfaz con una inferencia y el flujo de entrada/salida afectado cuando el modelo esté disponible.
