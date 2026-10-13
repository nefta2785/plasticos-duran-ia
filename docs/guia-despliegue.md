# Guía de despliegue en producción (VM de Oracle)

Cómo poner en marcha **duranPROD** (Odoo 19 Community + PostgreSQL 15 + nginx, todo en Docker)
en la VM de Oracle, con HTTPS por IP, y cómo operarla después.

> **Cómo leer esta guía.** Cada paso dice:
> - **Dónde:** en qué máquina se escribe el comando: **Mac** (tu computadora), **VM** (el
>   servidor de Oracle, después de entrar por SSH) o **Navegador**.
> - El **comando** exacto, en un recuadro. Lo que va entre `<ángulos>` lo cambias tú.
> - **Qué hace**, en una frase.
> - **Cómo saber que salió bien.**
>
> Los pasos marcados con ⚠️ **Sin verificar** no están confirmados en documentación oficial ni
> probados en la VM: hazlos con calma y revisa el resultado antes de seguir. (⚠️ se usa **solo**
> para eso.)
>
> 🚫 marca algo que **no** se debe hacer.
>
> ✅ **Verificado el 12-oct-2026 en la VM** marca lo que ya se probó en la VM real.
>
> **Nunca** pegues contraseñas, el contenido de `.env` ni el de `odoo.conf` en un chat, un
> issue o un commit.

## Índice

0. [Datos de partida](#0-datos-de-partida)
1. [Entrar a la VM y revisar lo básico](#1-entrar-a-la-vm-y-revisar-lo-básico)
2. [Firewall: Oracle y la VM](#2-firewall-oracle-y-la-vm)
3. [Clonar el repo y preparar los archivos de configuración](#3-clonar-el-repo-y-preparar-los-archivos-de-configuración)
4. [Primer arranque, solo con el puerto 80](#4-primer-arranque-solo-con-el-puerto-80)
5. [Certificado HTTPS con Certbot](#5-certificado-https-con-certbot)
6. [Crear duranPROD por túnel SSH](#6-crear-duranprod-por-túnel-ssh)
7. [Encender HTTPS](#7-encender-https)
8. [web.base.url y report.url](#8-webbaseurl-y-reporturl)
9. [Configuración previa de Odoo](#9-configuración-previa-de-odoo)
10. [Instalar los módulos de Plásticos Durán](#10-instalar-los-módulos-de-plásticos-durán)
11. [Comprobaciones finales](#11-comprobaciones-finales)
12. [Qué hacer si cambia la IP](#12-qué-hacer-si-cambia-la-ip)
13. [Respaldos](#13-respaldos)
14. [Restauración probada (ensayo en la Mac)](#14-restauración-probada-ensayo-en-la-mac)
15. [Operación del día a día](#15-operación-del-día-a-día)
16. [Si algo falla](#16-si-algo-falla)
17. [Lo que no está verificado](#17-lo-que-no-está-verificado)
18. [Fuentes](#18-fuentes)

---

## 0. Datos de partida

| Dato | Valor |
|---|---|
| VM | Oracle, Ubuntu 22.04, ARM64 (aarch64), 2 OCPU, 12 GB RAM, Docker y Compose instalados |
| IP pública | `160.34.211.158` (efímera, sin dominio) |
| Usuario de la VM | `ubuntu` ✅ **Verificado el 12-oct-2026 en la VM** (Ubuntu 22.04.5 aarch64, Docker 29.9) |
| Firewall | 80 y 443 abiertos en Oracle y en iptables ✅ **Verificado el 12-oct-2026 en la VM**, incluida una prueba de reinicio (sección 2) |
| Carpeta del repo en la VM | `/home/ubuntu/plasticos-duran-ia` |
| Base de datos | `duranPROD` |
| Imágenes | Las mismas probadas en DEV, fijadas por digest en `docker/prod/docker-compose.yml`: Odoo 19.0-20260908, PostgreSQL 15.19, nginx 1.30.5 |

Archivos de producción (todos en `docker/prod/`):

| Archivo | Para qué |
|---|---|
| `docker-compose.yml` | Los tres servicios. Solo nginx publica puertos (80 y 443) |
| `docker-compose.tunel.yml` | Solo para el paso 6: publica Odoo en `127.0.0.1:8069` de la VM |
| `.env.example` → `.env` | Usuario y contraseña de PostgreSQL, y qué configuración de nginx usar. **`.env` no se versiona** |
| `odoo.conf.example` → `odoo.conf` | Configuración de Odoo. **`odoo.conf` no se versiona** (lleva el hash de la Master Password) |
| `nginx/http.conf` | nginx antes del certificado: solo puerto 80 |
| `nginx/https.conf` | nginx completo: 80 (redirección) y 443 (Odoo) |
| `certbot/recargar-nginx.sh` | Lo corre Certbot después de cada renovación: recarga nginx |
| `scripts/respaldo.sh` | Respaldo diario (base + filestore) con rotación de 14 |
| `scripts/restaurar.sh` | Restaura un respaldo en una base nueva |
| `cron/duran-respaldo` | Programa el respaldo diario |

---

## 1. Entrar a la VM y revisar lo básico

### 1.1 Entrar por SSH

**Dónde:** Mac

```
ssh ubuntu@160.34.211.158
```

**Qué hace:** abre una terminal dentro de la VM. Todos los pasos marcados "VM" se escriben ahí.

**Cómo saber que salió bien:** el prompt cambia a algo como `ubuntu@<nombre-de-la-vm>:~$`.

### 1.2 Revisar arquitectura, Docker y Compose

**Dónde:** VM

```
uname -m
docker version --format '{{.Server.Version}}'
docker compose version
```

**Qué hace:** confirma que la VM es ARM64 y que Docker y Compose responden.

**Cómo saber que salió bien:** `aarch64`, una versión de Docker (29.x) y una de Compose.

### 1.3 Que tu usuario pueda usar Docker sin sudo

**Dónde:** VM

```
groups
```

**Qué hace:** muestra a qué grupos perteneces.

**Cómo saber que salió bien:** en la lista aparece `docker`. Si **no** aparece:

```
sudo usermod -aG docker ubuntu
exit
```

y vuelve a entrar (paso 1.1). Hace falta para el respaldo automático (corre como `ubuntu`).

### 1.4 Que Docker arranque solo al prender la VM

**Dónde:** VM

```
systemctl is-enabled docker
```

**Cómo saber que salió bien:** responde `enabled`. Si no: `sudo systemctl enable docker`.

---

## 2. Firewall: Oracle y la VM

El tráfico tiene **dos** filtros y los dos deben dejar pasar los puertos 80 y 443:
1. La **Security List** (o el NSG) de la red de Oracle.
2. El **iptables** de la propia VM.

El 80 se queda abierto siempre: Let's Encrypt renueva el certificado por ahí cada pocos días.

> ✅ **Verificado el 12-oct-2026 en la VM** (Ubuntu 22.04.5 aarch64, Docker 29.9, usuario
> `ubuntu`): el procedimiento de los pasos 2.1 a 2.8, incluida la prueba de reinicio (2.8).
> El paso 2.9 (opcional) no se ha ejecutado.
>
> ⚠️ **Sin verificar:** la redacción exacta del `sed` de 2.5 y de los comandos de prueba de 2.7
> se escribió después, a partir de lo que se hizo en la VM. El `sed` se probó con GNU sed sobre
> una copia de ejemplo de `rules.v4` (no sobre el archivo real). Revisa la salida del `grep` de
> 2.5 antes de seguir.

**Lo que se encontró en la VM antes de abrir nada** (12-oct-2026):
- Las reglas se cargan al arrancar con **netfilter-persistent** desde
  `/etc/iptables/rules.v4`. Ese archivo **no** tiene cadenas de Docker (es anterior a Docker).
- **ufw** no se usa: el servicio aparece "active", pero `sudo ufw status` dice `inactive` y
  `/etc/ufw/ufw.conf` tiene `ENABLED=no`. No se toca.
- La cadena INPUT trae, en orden: `RELATED,ESTABLISHED`; `icmp`; `lo`; `8069` (resto de otro
  proyecto, ver 2.9); `22`; y al final un `REJECT --reject-with icmp-host-prohibited`.
- 80 y 443 estaban **cerrados** hasta que se abrieron con los pasos 2.4 y 2.5.

> 🚫 **No uses `ufw`** en esta VM: Oracle advierte que editar reglas con UFW en sus imágenes de
> Ubuntu puede dejar la instancia sin arrancar.
>
> 🚫 **No uses `sudo netfilter-persistent save`** (es lo que dice el tutorial de Oracle; esta
> guía lo usaba antes). Guarda **todo** el estado actual de iptables, incluidas las cadenas que
> Docker crea al arrancar (`DOCKER`, `DOCKER-FORWARD`, etc.). En el siguiente reinicio esas
> cadenas se cargarían desde el archivo y Docker las volvería a crear, y podrían duplicarse o
> chocar. ⚠️ **Sin verificar:** esto es una **precaución**, no algo que se haya visto fallar. Por
> eso aquí se editan solo las dos líneas necesarias en `rules.v4` (paso 2.5).

### 2.1 Security List de Oracle

**Dónde:** Navegador (consola de Oracle Cloud)

Networking › Virtual Cloud Networks › tu VCN › la subred de la VM › Security List › **Add
Ingress Rules** (Agregar reglas de entrada). Agrega **dos reglas separadas**:

| Source CIDR (CIDR de origen) | IP Protocol | Source Port Range (rango de puertos de **origen**) | Destination Port Range (rango de puertos de **destino**) |
|---|---|---|---|
| `0.0.0.0/0` | TCP | **vacío** (Todo) | `80` |
| `0.0.0.0/0` | TCP | **vacío** (Todo) | `443` |

**Qué hace:** deja entrar a la VM las conexiones web desde internet.

> **Error ya visto:** poner `80` en el puerto de **origen** y `443` en el de **destino** en la
> misma regla **no abre nada**: el puerto de origen lo elige el navegador al azar, nunca es 80.
> El puerto va **solo** en destino, y cada puerto en su propia regla.

**Cómo saber que salió bien:** en la tabla de Ingress Rules hay dos reglas nuevas con CIDR de
origen `0.0.0.0/0`, protocolo TCP, la columna del rango de puertos de **origen** dice **Todo**
(All) y la de **destino** dice `80` en una y `443` en la otra. Si la VM usa un **Network
Security Group** en lugar de (o además de) la Security List, las reglas van ahí.

### 2.2 Ver cómo está iptables en la VM (diagnóstico, no cambia nada)

**Dónde:** VM

```
sudo iptables -L INPUT -n --line-numbers
systemctl is-active netfilter-persistent
sudo ufw status
```

**Qué hace:** lista las reglas de entrada numeradas, y muestra si netfilter-persistent está
activo y si ufw está en uso.

**Cómo saber qué tienes:** busca la línea `REJECT ... reject-with icmp-host-prohibited` y
**anota su número** (en la VM, el 12-oct-2026, era la **6**). Todo lo que no esté permitido
**antes** de esa línea se rechaza. netfilter-persistent debe decir `active`, y ufw `inactive`.

### 2.3 Copia de seguridad del archivo de reglas

**Dónde:** VM

```
sudo cp -a /etc/iptables/rules.v4 /etc/iptables/rules.v4.bak-$(date +%Y%m%d)
ls -l /etc/iptables/
```

**Qué hace:** guarda una copia del archivo que se carga al arrancar, con la fecha en el nombre.

**Cómo saber que salió bien:** aparece `rules.v4.bak-AAAAMMDD` (la fecha de hoy) con el mismo
tamaño que `rules.v4`. Si algo sale mal en 2.5, se recupera con
`sudo cp -a /etc/iptables/rules.v4.bak-AAAAMMDD /etc/iptables/rules.v4`.

### 2.4 Abrir 80 y 443 en vivo

**Dónde:** VM

Sustituye `<N>` por el número de la línea `REJECT` que anotaste en 2.2, y `<N+1>` por ese número
más uno (en la VM fueron `6` y `7`):

```
sudo iptables -I INPUT <N> -p tcp -m state --state NEW --dport 80 -j ACCEPT
sudo iptables -I INPUT <N+1> -p tcp -m state --state NEW --dport 443 -j ACCEPT
sudo iptables -L INPUT -n --line-numbers
```

**Qué hace:** inserta las dos reglas justo antes del `REJECT` (al insertar la del 80, el `REJECT`
baja una posición; por eso la del 443 va en `<N+1>`). Esto cambia las reglas **en memoria**: si
la VM se reinicia ahora, se pierden. El paso 2.5 las guarda.

**Cómo saber que salió bien:** en la lista aparecen `tcp dpt:80` y `tcp dpt:443` con `ACCEPT`,
**una vez cada una**, y **antes** del `REJECT`.

> **No pegues dos veces** los comandos `iptables -I`: cada vez agregan otra regla igual. Si quedó
> duplicada, bórrala por su número con `sudo iptables -D INPUT <n>`. Si hay que borrar varias,
> empieza por la de **número más alto**: al borrar una, las de abajo suben una posición.

### 2.5 Guardar las dos reglas en `rules.v4`

**Dónde:** VM

```
sudo sed -i \
  -e '/^-A INPUT -j REJECT --reject-with icmp-host-prohibited$/i -A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT' \
  -e '/^-A INPUT -j REJECT --reject-with icmp-host-prohibited$/i -A INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT' \
  /etc/iptables/rules.v4
sudo grep -n -E -- '--dport (80|443) |REJECT' /etc/iptables/rules.v4
```

**Qué hace:** escribe en el archivo que se carga al arrancar las mismas dos reglas, justo antes
de la línea `-A INPUT -j REJECT --reject-with icmp-host-prohibited`. No toca nada más (el
`REJECT` de FORWARD no cambia) y no guarda las cadenas de Docker.

**Cómo saber que salió bien:** `grep` muestra, seguidas, las líneas `--dport 80` y
`--dport 443` e inmediatamente después `-A INPUT -j REJECT ...`; cada una **una sola vez**.
Si `sed` se corrió dos veces y quedaron repetidas, recupera la copia de 2.3 y repite este paso.

### 2.6 Validar la sintaxis del archivo

**Dónde:** VM

```
sudo sh -c 'iptables-restore --test < /etc/iptables/rules.v4' && echo "SINTAXIS OK"
```

**Qué hace:** pide a iptables que lea el archivo **sin aplicarlo**, para comprobar que no tiene
errores. La redirección `<` va **dentro** de `sudo sh -c '...'`: escrita afuera
(`sudo iptables-restore --test < ...`), la lee tu usuario sin permisos y da "Permission denied".

**Cómo saber que salió bien:** imprime `SINTAXIS OK`. Si da error, **no reinicies**: recupera la
copia de 2.3.

### 2.7 Probar desde internet con un servidor temporal

Todavía no hay nada escuchando en 80 ni en 443 (el Docker de producción se levanta en el paso 4),
así que se usa un servidor de prueba de Python que se apaga solo a los 2 minutos.

**Dónde:** VM

```
mkdir -p /tmp/vacio
sudo timeout 120 python3 -m http.server 80 --directory /tmp/vacio &
sudo timeout 120 python3 -m http.server 443 --directory /tmp/vacio &
sleep 2
sudo ss -tlnp | grep -E ':(80|443) '
```

**Qué hace:** levanta dos servidores web vacíos (en el 443 también es HTTP simple, sin
certificado) y comprueba que ya están escuchando.

**Cómo saber que salió bien (VM):** `ss` muestra `python3` en `:80` y en `:443`. **Solo entonces**
pasa a la Mac: si el servidor no está arriba, el `curl` falla en milisegundos y **parece** un
problema de firewall sin serlo.

**Dónde:** Mac (antes de que pasen los 2 minutos)

```
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 http://160.34.211.158/
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 http://160.34.211.158:443/
```

**Qué hace:** se conecta desde internet a los dos puertos (al 443 con `http://` porque el
servidor de prueba no tiene certificado).

**Cómo saber que salió bien:** los dos responden `200`. Si tarda los 10 segundos y falla
(*timeout*), algo sigue bloqueando: revisa 2.1 y 2.4. Si falla **al instante** con
*connection refused*, el servidor de prueba ya no estaba arriba: repite la parte de la VM.

Al terminar, los servidores se apagan solos (por el `timeout 120`). Para confirmarlo, en la VM:
`sudo ss -tlnp | grep -E ':(80|443) '` no muestra nada.

### 2.8 Prueba de reinicio

**Dónde:** VM

```
sudo reboot
```

Espera un par de minutos, vuelve a entrar (paso 1.1) y:

```
sudo iptables -L INPUT -n --line-numbers
systemctl is-active docker netfilter-persistent
```

**Qué hace:** comprueba que las reglas se cargan solas desde `rules.v4` al arrancar.

**Cómo saber que salió bien:** `tcp dpt:80` y `tcp dpt:443` siguen apareciendo **antes** del
`REJECT`, una vez cada una, y los dos servicios dicen `active`.

> ⚠️ **Sin verificar:**
> - Que este procedimiento sirva igual en **otra** VM (otra imagen u otra versión de Ubuntu
>   puede traer otras reglas, otra posición del `REJECT` u otro archivo). Repite el diagnóstico
>   de 2.2 antes de copiar números de línea.
> - Si nginx **en Docker** necesita estas reglas de INPUT: Docker dirige el tráfico de los puertos
>   publicados por la tabla `nat`, antes de la cadena INPUT (documentación de Docker). La prueba
>   de 2.7 usó un servidor **fuera** de Docker, que sí pasa por INPUT. Las reglas se dejan de
>   todos modos: las necesita cualquier cosa que escuche directo en la VM y dejan claro qué está
>   permitido.

### 2.9 (Opcional, después del despliegue) Quitar la regla vieja del 8069

La regla del puerto **8069**, en Oracle y en iptables, es un resto del Odoo de otro proyecto.
Producción no la necesita: Odoo no publica puertos y el túnel del paso 6 usa `127.0.0.1` (la
interfaz `lo`, que se permite con otra regla). Quitarla es **opcional**; hazlo solo con todo ya
funcionando (paso 11).

> ⚠️ **Sin verificar:** estos pasos no se han ejecutado en la VM. Están armados con las mismas
> herramientas que 2.3 a 2.8.

**Oracle — Dónde:** Navegador. En la Security List (2.1), busca la regla de entrada con destino
`8069`, revisa que sea esa (y no la de 80, 443 o 22) y elimínala.
**Cómo saber que salió bien:** en Ingress Rules ya no aparece ningún destino `8069`, y siguen las
de 22, 80 y 443.

**VM — Dónde:** VM

1. Copia de seguridad (como en 2.3):
   ```
   sudo cp -a /etc/iptables/rules.v4 /etc/iptables/rules.v4.bak-$(date +%Y%m%d)-sin8069
   ```
2. Quitarla en vivo. Busca su número y bórrala por número:
   ```
   sudo iptables -L INPUT -n --line-numbers | grep 'dpt:8069'
   sudo iptables -D INPUT <n>
   ```
   **Cómo saber que salió bien:** `sudo iptables -L INPUT -n --line-numbers` ya no muestra
   `dpt:8069`, y siguen `dpt:22`, `dpt:80`, `dpt:443` y el `REJECT`.
3. Quitarla del archivo. Busca su número de línea y bórrala por número:
   ```
   sudo grep -n -- '--dport 8069' /etc/iptables/rules.v4
   sudo sed -i '<L>d' /etc/iptables/rules.v4
   sudo grep -c -- '--dport 8069' /etc/iptables/rules.v4
   ```
   (`<L>` es el número que mostró el primer `grep`, sin los dos puntos.)
   **Cómo saber que salió bien:** el último `grep` responde `0`.
4. Validar (como en 2.6) y, si quieres, repetir la prueba de reinicio (2.8):
   ```
   sudo sh -c 'iptables-restore --test < /etc/iptables/rules.v4' && echo "SINTAXIS OK"
   ```

---

## 3. Clonar el repo y preparar los archivos de configuración

### 3.1 Clonar

**Dónde:** VM

```
cd /home/ubuntu
git clone https://github.com/nefta2785/plasticos-duran-ia.git
cd plasticos-duran-ia
git log --oneline -1
```

**Qué hace:** descarga el repo (rama `main`).

**Cómo saber que salió bien:** el último commit es el más reciente de `main` en GitHub.

> ⚠️ **Sin verificar:** si el repo es privado, `git clone` pedirá credenciales. Lo recomendable es
> una *deploy key* de solo lectura (GitHub › repo › Settings › Deploy keys) en lugar de tu
> contraseña o un token personal.

### 3.2 Crear `.env`

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
cp .env.example .env
chmod 600 .env
openssl rand -base64 32
nano .env
```

**Qué hace:** crea tu `.env` (solo tú puedes leerlo), genera una contraseña aleatoria para
PostgreSQL y abre el editor.

En el editor cambia `POSTGRES_USER=CAMBIAR` (por ejemplo `odoo`) y `POSTGRES_PASSWORD=CAMBIAR`
(pega la contraseña que generó `openssl`). Deja `NGINX_CONF=http`. Guarda con `Ctrl+O`, `Enter`,
y sal con `Ctrl+X`. Guarda también esa contraseña en tu gestor de contraseñas.

**Cómo saber que salió bien:**

```
grep -c CAMBIAR .env
```

responde `0`.

### 3.3 Crear `odoo.conf` con el hash de la Master Password

La Master Password protege el gestor de bases. En `odoo.conf` se guarda **solo su hash**, nunca
la contraseña. El hash se genera en la VM: la contraseña la escribes tú, no aparece en pantalla
ni queda en el historial, y no pasa por ningún chat.

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
cp odoo.conf.example odoo.conf
docker run --rm -it --network none --entrypoint python3 \
  odoo@sha256:c716703f64af06c191c00669f5904b6dbaa2e6ec1a731a584ec27fa7ea935ece \
  -c "import getpass; from odoo.tools.config import crypt_context; print(crypt_context.hash(getpass.getpass('Master Password: ')))"
```

**Qué hace:** usa la misma imagen de Odoo (sin red) para calcular el hash con el mismo método
que Odoo usa para verificarla. Pide la contraseña sin mostrarla e imprime una línea que empieza
con `$pbkdf2-sha512$600000$`.

Elige una Master Password larga y guárdala en tu gestor de contraseñas **antes** de cerrar la
terminal. Después:

```
nano odoo.conf
```

En la línea `admin_passwd =` pega el hash después del `=` y un espacio. Guarda y sal.

**Cómo saber que salió bien:**

```
grep -c '^admin_passwd = \$pbkdf2-sha512\$' odoo.conf
```

responde `1`.

> Por qué no se deja un texto de ejemplo: en Odoo 19, si `admin_passwd` tiene un texto que no es
> hash, Odoo lo acepta como contraseña **en texto plano**. Vacío, en cambio, bloquea el gestor
> (verificado en la imagen de Odoo 19). Por eso `odoo.conf.example` lo trae vacío.

`odoo.conf` se deja con los permisos que trae (`644`): el contenedor de Odoo corre con otro
usuario y necesita leerlo. Contiene el hash, no la contraseña.

---

## 4. Primer arranque, solo con el puerto 80

En este momento nginx **no** pasa nada a Odoo: solo responde "en preparación" y sirve el reto
de Let's Encrypt. Así, nada de Odoo queda expuesto mientras no hay HTTPS ni base.

### 4.1 Carpetas que comparte Certbot con nginx

**Dónde:** VM

```
sudo mkdir -p /etc/letsencrypt /var/www/certbot
```

**Qué hace:** crea la carpeta donde Certbot guardará los certificados y la del reto HTTP-01.

**Cómo saber que salió bien:** `ls -d /etc/letsencrypt /var/www/certbot` muestra las dos.

### 4.2 Descargar las imágenes y arrancar

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
docker compose pull
docker compose up -d
docker compose ps
```

**Qué hace:** descarga las tres imágenes (versión ARM64) y arranca db, odoo y nginx.

**Cómo saber que salió bien:** `docker compose ps` muestra los tres servicios; `db` como
`healthy`, y en `PORTS` solo nginx tiene `0.0.0.0:80->80/tcp` y `0.0.0.0:443->443/tcp`.

### 4.3 Revisar que Odoo arrancó

**Dónde:** VM

```
docker compose logs --tail 50 odoo
```

**Cómo saber que salió bien:** no hay líneas con `ERROR` ni `CRITICAL` y el contenedor no se
reinicia (en `docker compose ps` su estado es `Up` y no `Restarting`).

### 4.4 Probar el puerto 80 desde fuera

**Dónde:** VM y luego Mac

En la VM, un archivo de prueba en la carpeta del reto:

```
sudo mkdir -p /var/www/certbot/.well-known/acme-challenge
echo prueba-ok | sudo tee /var/www/certbot/.well-known/acme-challenge/prueba
```

En la Mac:

```
curl -i http://160.34.211.158/.well-known/acme-challenge/prueba
curl -i http://160.34.211.158/
```

**Qué hace:** comprueba desde internet que el 80 está abierto y que nginx sirve el reto.

**Cómo saber que salió bien:** el primero responde `200` con `prueba-ok`; el segundo, `503` con
"Plasticos Duran: en preparacion". Si tarda y termina en *timeout*, el puerto está cerrado: ver
[16.2](#162-certbot-dice-timeout-o-el-puerto-80-no-responde).

Borra el archivo de prueba (**Dónde:** VM):

```
sudo rm /var/www/certbot/.well-known/acme-challenge/prueba
```

---

## 5. Certificado HTTPS con Certbot

Let's Encrypt da certificados para una IP solo con el perfil **shortlived** (dura unos 6 días,
160 horas). Certbot lo pide con `--ip-address` y `--preferred-profile shortlived`; con el plugin
**webroot** hace falta **Certbot 5.4 o más nuevo**. Primero se prueba con **staging** (el
servidor de pruebas, que no cuenta para los límites).

### 5.1 Instalar Certbot por snap

**Dónde:** VM

```
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/local/bin/certbot
certbot --version
```

**Qué hace:** instala Certbot (método recomendado por Certbot) y lo deja en el PATH.

**Cómo saber que salió bien:** `certbot --version` muestra **5.4.0 o mayor**. Si es menor, no
sigas: `sudo snap refresh certbot` y vuelve a revisar.

> ⚠️ **Sin verificar:** qué versión entrega el snap en ARM64 el día que lo instales (la página
> de Certbot dice que el snap soporta "ARMv8").

### 5.2 Certificado de prueba (staging)

**Dónde:** VM

```
sudo certbot certonly --staging --webroot -w /var/www/certbot \
  --ip-address 160.34.211.158 --preferred-profile shortlived \
  --cert-name duran-ip \
  --deploy-hook /home/ubuntu/plasticos-duran-ia/docker/prod/certbot/recargar-nginx.sh
```

**Qué hace:** pide un certificado **de prueba** para la IP. Certbot deja un archivo en
`/var/www/certbot/.well-known/acme-challenge/` y Let's Encrypt lo descarga por el puerto 80 para
comprobar que controlas la IP. La primera vez te pide un correo (opcional) y aceptar los términos.

**Cómo saber que salió bien:** termina con "Successfully received certificate", y

```
sudo certbot certificates
```

muestra `duran-ip` con `INVALID: TEST_CERT` (correcto: es de staging) y una caducidad de unos
6 días.

### 5.3 Certificado real

**Dónde:** VM

```
sudo certbot delete --cert-name duran-ip
sudo certbot certonly --webroot -w /var/www/certbot \
  --ip-address 160.34.211.158 --preferred-profile shortlived \
  --cert-name duran-ip \
  --deploy-hook /home/ubuntu/plasticos-duran-ia/docker/prod/certbot/recargar-nginx.sh
```

**Qué hace:** borra el de prueba y pide el real con los mismos datos. El `--deploy-hook` queda
guardado y Certbot lo corre después de cada renovación.

**Cómo saber que salió bien:** `sudo certbot certificates` muestra `duran-ip` con
`VALID: 6 days` (o 5, según la hora), **sin** `TEST_CERT`, y la ruta
`/etc/letsencrypt/live/duran-ip/fullchain.pem`.

> Si pide confirmar porque "ya existe una cuenta" o un certificado, responde que sí: staging y
> producción usan cuentas distintas.

### 5.4 Renovación automática

**Dónde:** VM

```
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

**Qué hace:** el primero muestra el *timer* de systemd que trae el snap y que corre la renovación
dos veces al día; el segundo simula una renovación contra staging sin tocar el certificado real.

**Cómo saber que salió bien:** aparece `snap.certbot.renew.timer` con su próxima ejecución, y el
*dry run* termina con "Congratulations, all simulated renewals succeeded".

Certbot renueva un certificado de 10 días o menos cuando le queda la **mitad** de su vida (unas
80 horas), o antes si Let's Encrypt lo indica por ARI. El `--dry-run` no corre el deploy-hook.

---

## 6. Crear duranPROD por túnel SSH

El gestor de bases **nunca** se publica en internet. Para crear la base se abre un túnel SSH
cifrado de la Mac a la VM, y Odoo se publica **solo** en el loopback de la VM (`127.0.0.1:8069`)
mientras dura este paso.

> **Por qué así (y no con la IP interna del contenedor):** la IP interna cambia cada vez que el
> contenedor se recrea; el loopback es fijo. Un puerto en `127.0.0.1` solo lo alcanza la propia
> VM: según la documentación de Docker, antes de Docker 28.0.0 equipos de la misma red local
> podían alcanzar estos puertos; la VM tiene Docker 29. Aun así, se publica **solo durante este
> paso** y se quita al terminar.

### 6.1 Encender el gestor temporalmente

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
sed -i 's/^list_db = False$/list_db = True/' odoo.conf
grep '^list_db' odoo.conf
```

**Qué hace:** permite usar el gestor de bases (solo se podrá llegar a él por el túnel: nginx
sigue en modo `http` y no pasa nada a Odoo).

**Cómo saber que salió bien:** muestra `list_db = True`.

### 6.2 Publicar Odoo en el loopback de la VM

**Dónde:** VM

```
docker compose -f docker-compose.yml -f docker-compose.tunel.yml up -d --force-recreate odoo
sudo ss -tlnp | grep 8069
```

**Qué hace:** recrea Odoo con el puerto 8069 publicado **solo** en `127.0.0.1` (y relee
`odoo.conf`).

**Cómo saber que salió bien:** `ss` muestra `127.0.0.1:8069` (y **no** `0.0.0.0:8069`).

### 6.3 Abrir el túnel

**Dónde:** Mac (una terminal nueva; déjala abierta)

```
ssh -N -L 18069:127.0.0.1:8069 ubuntu@160.34.211.158
```

**Qué hace:** todo lo que abras en `localhost:18069` de la Mac viaja cifrado por SSH hasta
`127.0.0.1:8069` de la VM. Se usa 18069 para no chocar con nada local (DEV usa 8071).

**Cómo saber que salió bien:** el comando se queda "pegado" sin mostrar nada: es normal.

### 6.4 Crear la base

**Dónde:** Navegador (en la Mac)

Abre `http://localhost:18069/web/database/manager` y llena el formulario de crear base, igual
que en DEV:

| Campo | Valor |
|---|---|
| Master Password | la del paso 3.3 |
| Database Name | `duranPROD` |
| Email | el usuario administrador |
| Password | una contraseña nueva y fuerte para ese administrador (a tu gestor de contraseñas) |
| Language | Español (MX) |
| Country | México |
| Demo Data | **sin marcar** |

**Qué hace:** crea la base duranPROD.

**Cómo saber que salió bien:** tras un par de minutos entras a Odoo como administrador.

### 6.5 Apagar el gestor y quitar el puerto

**Dónde:** Mac (en la terminal del túnel) y VM

En la terminal del túnel: `Ctrl+C` para cerrarlo. Luego, en la VM:

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
sed -i 's/^list_db = True$/list_db = False/' odoo.conf
grep '^list_db' odoo.conf
docker compose up -d --force-recreate odoo
sudo ss -tlnp | grep 8069
```

**Qué hace:** vuelve a `list_db = False` (el gestor queda apagado por completo, también por
XML-RPC) y recrea Odoo **sin** el archivo del túnel, lo que quita el puerto.

**Cómo saber que salió bien:** `grep` muestra `list_db = False` y `ss` **no muestra nada**.

---

## 7. Encender HTTPS

### 7.1 Cambiar nginx a la configuración completa

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
sed -i 's/^NGINX_CONF=http$/NGINX_CONF=https/' .env
grep '^NGINX_CONF' .env
docker compose up -d nginx
docker compose logs --tail 20 nginx
```

**Qué hace:** monta `nginx/https.conf` (80 redirige a 443; 443 lleva a Odoo con el certificado)
y recrea nginx.

**Cómo saber que salió bien:** `NGINX_CONF=https`, y en los logs de nginx no hay `emerg` ni
`cannot load certificate`.

### 7.2 Probar desde fuera

**Dónde:** Mac

```
curl -sI http://160.34.211.158/ | head -3
curl -sI https://160.34.211.158/web/login | head -1
curl -s -o /dev/null -w '%{http_code}\n' https://160.34.211.158/web/database/manager
```

**Qué hace:** comprueba la redirección a HTTPS, que Odoo responde por HTTPS y que el gestor de
bases está bloqueado.

**Cómo saber que salió bien:** `301` con `Location: https://160.34.211.158/`; `HTTP/2 200` en
`/web/login`; y `403` en el gestor. En el navegador, `https://160.34.211.158` muestra el
candado **sin** advertencias.

---

## 8. web.base.url y report.url

Odoo usa `web.base.url` para armar enlaces (correos, PDF, etc.). Si no se fija, Odoo lo
reescribe cada vez que entra un administrador (por ejemplo, quedó como `http://localhost:18069`
al entrar por el túnel). `report.url` hace que los PDF tomen su estilo desde dentro del
contenedor en lugar de salir a la IP pública.

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
docker compose run --rm -T odoo odoo shell -d duranPROD --no-http <<'EOF'
ICP = env['ir.config_parameter'].sudo()
ICP.set_param('web.base.url', 'https://160.34.211.158')
ICP.set_param('web.base.url.freeze', 'True')
ICP.set_param('report.url', 'http://localhost:8069')
env.cr.commit()
print('web.base.url =', ICP.get_param('web.base.url'))
print('web.base.url.freeze =', ICP.get_param('web.base.url.freeze'))
print('report.url =', ICP.get_param('report.url'))
EOF
```

**Qué hace:** abre una consola de Odoo sobre duranPROD (en un contenedor temporal), guarda los
tres parámetros y los imprime.

**Cómo saber que salió bien:** al final se imprimen los tres valores tal cual. También se ven en
Ajustes › Técnico › Parámetros del sistema (modo desarrollador).

---

## 9. Configuración previa de Odoo

**Dónde:** Navegador (`https://160.34.211.158`, como administrador)

1. En **Aplicaciones**, instala **Ventas**, **Inventario** y **Facturación** (los módulos de
   Plásticos Durán dependen de ellas).
2. Sigue los pasos **1 a 5** de [configuracion-produccion.md](configuracion-produccion.md)
   ("Lista para duranPROD"). **Todavía no des de alta productos.**

**Cómo saber que salió bien:** cada ajuste queda como dice esa lista.

---

## 10. Instalar los módulos de Plásticos Durán

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
docker compose stop odoo
docker compose run --rm odoo odoo -d duranPROD -i duran_peso_variable,duran_captura_tianguis --stop-after-init --no-http
docker compose up -d odoo
```

**Qué hace:** detiene Odoo, instala los dos módulos en duranPROD en un contenedor temporal (que
se apaga al terminar) y vuelve a arrancar Odoo.

**Cómo saber que salió bien:** el comando de en medio termina sin líneas `ERROR`; en
Aplicaciones aparecen los dos módulos como instalados; y `https://160.34.211.158/captura` abre
(con un usuario del grupo "Captura tianguis").

Después, sigue los pasos **6 y 7** de [configuracion-produccion.md](configuracion-produccion.md)
(parámetros de peso y unidad kg).

---

## 11. Comprobaciones finales

Todas desde la **Mac**, salvo que se diga otra cosa.

### 11.1 El service worker de /captura llega con su encabezado a través de nginx

```
curl -sI https://160.34.211.158/captura/sw.js
```

**Cómo saber que salió bien:** `HTTP/2 200`, `content-type: text/javascript` y
`service-worker-allowed: /captura`. Sin ese encabezado, el navegador no deja registrar el service
worker con alcance `/captura`.

### 11.2 Manifiesto e íconos

```
curl -sI https://160.34.211.158/duran_captura_tianguis/static/captura.webmanifest | grep -i content-type
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://160.34.211.158/duran_captura_tianguis/static/img/icono-512.png
```

**Cómo saber que salió bien:** `application/manifest+json` y `200 image/png`.

### 11.3 Websocket (puerto 8072 de Odoo, vía nginx)

```
curl -s https://160.34.211.158/websocket/health
```

**Cómo saber que salió bien:** responde `{"status": "pass"}`.

### 11.4 Renovación del certificado

**Dónde:** VM

```
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

**Cómo saber que salió bien:** como en el paso 5.4.

### 11.5 El certificado no vence pronto

```
echo | openssl s_client -connect 160.34.211.158:443 2>/dev/null | openssl x509 -noout -enddate -checkend 172800
```

**Qué hace:** muestra la fecha de vencimiento y revisa si vence en menos de 48 horas.

**Cómo saber que salió bien:** `notAfter=...` y `Certificate will not expire`. Si dice
`Certificate will expire`, ver [16.6](#166-el-certificado-no-se-renueva).

### 11.6 Reinicio completo

**Dónde:** VM

```
sudo reboot
```

Espera un par de minutos y repite 11.1 y 11.5 desde la Mac.

**Cómo saber que salió bien:** todo responde igual sin haber hecho nada más.

### 11.7 En el celular

**Dónde:** el celular Android (Chrome)

Abre `https://160.34.211.158/captura`, inicia sesión y en el menú ⋮ elige **Instalar app**.

**Cómo saber que salió bien:** aparece el ícono azul con la "D" en la pantalla de inicio y la app
abre sin barra de direcciones.

> ⚠️ **Sin verificar:** que Chrome en Android ofrezca "Instalar app" con este certificado y esta
> configuración solo se puede comprobar en el celular. Si no aparece la opción, la alternativa
> es la opción del menú ⋮ para agregar la página a la pantalla de inicio (abre como pestaña de
> Chrome, no como app).

---

## 12. Qué hacer si cambia la IP

La IP es **efímera**: según Oracle, se conserva si la VM se **detiene**, pero se pierde si la
instancia se **termina** o se desconecta su VNIC, y no se puede convertir en reservada. Si un día
la VM tiene otra IP (`<IP_NUEVA>`):

1. **Firewall** (Navegador): las reglas del paso 2 no dependen de la IP; no cambian.
2. **Certificado** (VM):
   ```
   sudo certbot certonly --webroot -w /var/www/certbot \
     --ip-address <IP_NUEVA> --preferred-profile shortlived \
     --cert-name duran-ip \
     --deploy-hook /home/ubuntu/plasticos-duran-ia/docker/prod/certbot/recargar-nginx.sh
   ```
   **Cómo saber que salió bien:** `sudo certbot certificates` muestra `duran-ip` con la IP nueva.
   ⚠️ **Sin verificar:** que Certbot acepte cambiar la IP del mismo `--cert-name` sin borrar
   antes el certificado; si se queja, `sudo certbot delete --cert-name duran-ip` y repite.
   Mientras no haya certificado válido, nginx no puede arrancar con `https`: si hace falta,
   vuelve temporalmente a `NGINX_CONF=http` (paso 7.1 al revés).
3. **web.base.url** (VM): repite el paso 8 con `https://<IP_NUEVA>`.
4. **Respaldos** (Mac): cambia la IP en el comando de `rsync` (paso 13.4).
5. **Celulares**: desinstala la app vieja y vuelve a instalarla desde
   `https://<IP_NUEVA>/captura` (paso 11.7). La app instalada guarda la dirección vieja.
6. **SSH** (Mac): la primera conexión a la IP nueva preguntará si confías en el servidor.
7. Repite las comprobaciones del paso 11.

---

## 13. Respaldos

Cada día, a las 03:30 (hora del centro de México), `respaldo.sh` guarda en la VM:
- `duranPROD.dump`: la base completa (`pg_dump` en formato custom).
- `filestore.tar.gz`: el filestore (adjuntos e imágenes; Odoo los guarda fuera de la base).

Conserva los **14** más recientes. La Mac los **jala** con `rsync` por SSH: la VM no guarda
credenciales de ningún otro lugar.

### 13.1 Carpeta de respaldos

**Dónde:** VM

```
sudo install -d -o ubuntu -g ubuntu -m 700 /var/backups/duran
```

**Qué hace:** crea `/var/backups/duran`, del usuario `ubuntu` y solo legible por él.

**Cómo saber que salió bien:** `ls -ld /var/backups/duran` muestra `drwx------ ubuntu ubuntu`.

### 13.2 Primer respaldo, a mano

**Dónde:** VM

```
/home/ubuntu/plasticos-duran-ia/docker/prod/scripts/respaldo.sh
ls -lR /var/backups/duran | head -20
```

**Qué hace:** corre el respaldo una vez para comprobar que funciona.

**Cómo saber que salió bien:** termina con "Respaldo listo: /var/backups/duran/AAAAMMDD-HHMMSS"
y esa carpeta tiene `duranPROD.dump` y `filestore.tar.gz`, los dos con tamaño mayor a 0.

### 13.3 Programarlo con cron

**Dónde:** VM

```
sudo install -o root -g root -m 644 /home/ubuntu/plasticos-duran-ia/docker/prod/cron/duran-respaldo /etc/cron.d/duran-respaldo
timedatectl | grep 'Time zone'
```

**Qué hace:** instala la tarea diaria (corre como `ubuntu` a las 09:30 UTC) y muestra la zona
horaria de la VM.

**Antes:** el paso 13.1 debe estar hecho. El cron escribe `respaldo.log` en
`/var/backups/duran`; si la carpeta no existe o no es de `ubuntu`, la tarea falla sin respaldo.

**Cómo saber que salió bien:** la zona es `Etc/UTC` (si es otra, ajusta la hora en
`/etc/cron.d/duran-respaldo`). Al día siguiente:

```
tail -5 /var/backups/duran/respaldo.log
```

muestra el respaldo de esa madrugada.

### 13.4 Copiarlos a la Mac

**Dónde:** Mac

```
mkdir -p ~/Respaldos/duranPROD
rsync -av ubuntu@160.34.211.158:/var/backups/duran/ ~/Respaldos/duranPROD/
```

**Qué hace:** copia a la Mac los respaldos nuevos (los que ya estaban no se vuelven a copiar).

**Cómo saber que salió bien:** `ls ~/Respaldos/duranPROD` muestra las mismas carpetas con fecha
que la VM.

Sin `--delete` a propósito: si en la VM se borra algo (por la rotación o por un problema), la
copia de la Mac no se borra. Los viejos de la Mac los borras tú cuando quieras.

Para que la Mac lo haga sola, por ejemplo cada día a las 10:00 (si la Mac está prendida):
`crontab -e` en la Mac y agrega
`0 10 * * * rsync -a ubuntu@160.34.211.158:/var/backups/duran/ $HOME/Respaldos/duranPROD/`.
⚠️ **Sin verificar:** en macOS, `cron` puede necesitar permiso de "Acceso total al disco" en
Ajustes del Sistema › Privacidad y seguridad.

### 13.5 Más adelante (no implementado): copia cifrada a Google Drive

Opción para tener una copia aunque la Mac esté apagada: instalar `rclone` en la VM con un remoto
de Google Drive y encima un remoto `crypt` (cifra nombres y contenido con una clave que solo tú
tienes), y agregar al final de `respaldo.sh` un `rclone copy` de la carpeta del día.
Consideraciones: la VM guardaría un token de Google Drive (si alguien entra a la VM, podría usar
ese Drive), y si se pierde la clave del `crypt`, los respaldos de Drive no se pueden abrir.
⚠️ **Sin verificar:** no se probó; revisar la documentación de rclone antes de implementarlo.

---

## 14. Restauración probada (ensayo en la Mac)

Un respaldo solo sirve si se puede restaurar. Este ensayo restaura el respaldo más reciente de
producción en una base **aparte**, `duranPRUEBA`, en el Docker de desarrollo de la Mac.
**Nunca** en duranDEV (`restaurar.sh` se niega a usar ese nombre, y nunca borra ni sobrescribe
una base existente).

> Mientras exista `duranPRUEBA`, `http://localhost:8071` mostrará el selector de bases de datos.
> Bórrala al terminar (paso 14.7).

### 14.1 Traer el respaldo

**Dónde:** Mac

```
rsync -av ubuntu@160.34.211.158:/var/backups/duran/ ~/Respaldos/duranPROD/
ls ~/Respaldos/duranPROD
```

**Cómo saber que salió bien:** ves la carpeta más reciente (`AAAAMMDD-HHMMSS`). Anótala.

### 14.2 Que el Docker de desarrollo esté arriba

**Dónde:** Mac

```
cd ~/Documents/plasticos-duran-ia/docker
docker compose ps
```

**Cómo saber que salió bien:** `db` y `odoo` en `Up` (`db` como `healthy`).

### 14.3 Restaurar en duranPRUEBA

**Dónde:** Mac

```
cd ~/Documents/plasticos-duran-ia
COMPOSE_DIR=docker docker/prod/scripts/restaurar.sh ~/Respaldos/duranPROD/<AAAAMMDD-HHMMSS> duranPRUEBA
```

**Qué hace:** crea la base `duranPRUEBA` en el PostgreSQL de desarrollo, carga el dump y copia el
filestore a `/var/lib/odoo/filestore/duranPRUEBA` (Odoo lo busca por el nombre de la base).

**Cómo saber que salió bien:** termina con "Listo: base duranPRUEBA restaurada." Si algo falla,
se detiene con un mensaje `ERROR` o de `pg_restore` (ver [16.9](#169-falla-la-restauración)).

### 14.4 Neutralizarla

**Dónde:** Mac

```
cd ~/Documents/plasticos-duran-ia/docker
docker compose exec -T odoo sh -c 'odoo neutralize -d duranPRUEBA --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD"'
```

**Qué hace:** desactiva en la copia lo que podría salir hacia afuera (correos, tareas
programadas, etc.). Es el comando de Odoo para "neutralizar una base de producción para pruebas".

**Cómo saber que salió bien:** termina sin `ERROR`.

### 14.5 Abrirla y revisarla

**Dónde:** Navegador (Mac)

Abre `http://localhost:8071`, elige `duranPRUEBA` en el selector y entra con el usuario
administrador **de producción**.

**Cómo saber que salió bien:**
- Están los clientes, productos y órdenes de producción.
- Una imagen de producto o un adjunto se ve (eso prueba el filestore).
- `/captura` abre con un usuario de tianguis.

### 14.6 Comparar conteos con producción

**Dónde:** VM y Mac (el mismo comando en las dos, cambiando la base)

En la VM (`docker/prod`), con `duranPROD`; en la Mac (`docker`), con `duranPRUEBA`:

```
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d <base> -Atc "SELECT (SELECT count(*) FROM res_partner), (SELECT count(*) FROM sale_order), (SELECT count(*) FROM ir_attachment)"'
```

**Cómo saber que salió bien:** los tres números son iguales, o la VM tiene un poco más si hubo
movimiento después del respaldo.

### 14.7 Borrar la base de prueba

**Dónde:** Mac. **Revisa dos veces que el nombre sea `duranPRUEBA`.**

```
cd ~/Documents/plasticos-duran-ia/docker
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" duranPRUEBA'
docker compose exec -T odoo rm -rf /var/lib/odoo/filestore/duranPRUEBA
```

**Cómo saber que salió bien:** `http://localhost:8071` vuelve a abrir directo duranDEV, sin
selector.

Anota la fecha del ensayo y el respaldo usado. Repítelo cada vez que cambie algo importante
(versión de Odoo, módulos nuevos) y al menos cada pocos meses.

### 14.8 Restaurar de verdad en producción (desastre)

⚠️ **Sin verificar:** no se ha ensayado todavía. En una VM nueva (o un stack limpio, sin base duranPROD), después de
los pasos 1 a 5:

```
cd /home/ubuntu/plasticos-duran-ia
docker/prod/scripts/restaurar.sh /var/backups/duran/<AAAAMMDD-HHMMSS> duranPROD
```

y luego los pasos 7, 8 (si cambió la IP) y 11. Si la base duranPROD vieja todavía existe,
`restaurar.sh` se niega: no se borra nada sin decidirlo antes con calma.

---

## 15. Operación del día a día

Todos en la **VM**, desde `/home/ubuntu/plasticos-duran-ia/docker/prod`.

| Para… | Comando | Salió bien si… |
|---|---|---|
| Ver el estado | `docker compose ps` | los tres en `Up`; `db` `healthy` |
| Ver errores de Odoo | `docker compose logs --tail 100 odoo` | sin `ERROR`/`CRITICAL` recientes |
| Reiniciar Odoo | `docker compose restart odoo` | `ps` lo muestra `Up` y la web responde |
| Reiniciar todo | `docker compose restart` | ídem |
| Revisar el certificado | el comando del paso 11.5 (desde la Mac) | `Certificate will not expire` |

### Actualizar tras un cambio en el repo (sin perder datos)

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
./scripts/respaldo.sh
git -C /home/ubuntu/plasticos-duran-ia pull
docker compose stop odoo
docker compose run --rm odoo odoo -d duranPROD -u duran_peso_variable,duran_captura_tianguis --stop-after-init --no-http
docker compose up -d
```

**Qué hace:** respalda primero, trae el código nuevo, actualiza los dos módulos en duranPROD (los
datos se conservan: `-u` actualiza, no reinstala) y vuelve a levantar todo (`up -d` también
aplica cambios del `docker-compose.yml`, si los hubo).

**Cómo saber que salió bien:** el respaldo termina en "Respaldo listo", el `-u` termina sin
`ERROR`, `docker compose ps` muestra todo `Up`, y `https://160.34.211.158/captura` abre (en el
celular, cierra y vuelve a abrir la app).

---

## 16. Si algo falla

### 16.1 El navegador dice que el certificado no es válido

- Si aún estás en el paso 5.2, es **normal**: el de staging no es de confianza. Sigue al 5.3.
- Si ya hiciste el 5.3: `sudo certbot certificates` (VM). Si dice `TEST_CERT`, quedó el de
  staging: `sudo certbot delete --cert-name duran-ip` y repite el 5.3; luego
  `docker compose exec nginx nginx -s reload`.
- Con el certificado de staging tampoco funcionan el service worker ni "Instalar app".

### 16.2 Certbot dice "Timeout" o el puerto 80 no responde

Un *timeout* casi siempre es firewall. Revisa en orden:
1. **Navegador:** las reglas de la Security List (paso 2.1): el puerto va en el rango de
   **destino**, y el de **origen** debe decir **Todo**.
2. **VM:** `sudo iptables -L INPUT -n --line-numbers` (paso 2.2): el `ACCEPT` del 80 debe ir
   antes del `REJECT`. Si no está después de un reinicio, falta en `/etc/iptables/rules.v4`
   (pasos 2.5 y 2.6).
3. **VM:** `docker compose ps` (nginx en `Up` con `0.0.0.0:80->80/tcp`) y `sudo ss -tlnp | grep ':80 '`.
4. **Mac:** `curl -v http://160.34.211.158/` y `nc -vz 160.34.211.158 80`. *Connection refused*
   (respuesta inmediata) = llega a la VM pero nada escucha; *timeout* = un firewall lo bloquea.
   Si pruebas con el servidor temporal de 2.7, confirma con `ss` que está **arriba** antes del
   `curl`: si no, el `curl` falla al instante y parece firewall sin serlo.

### 16.3 Certbot no reconoce `--ip-address` o `--preferred-profile`

La versión es vieja. `certbot --version` debe ser 5.4.0 o mayor: `sudo snap refresh certbot`.
Revisa también que no haya un Certbot de `apt` (`apt list --installed 2>/dev/null | grep certbot`);
si lo hay, `sudo apt-get remove certbot`.

### 16.4 nginx no arranca después de cambiar a `https`

`docker compose logs --tail 30 nginx` (VM). Si dice `cannot load certificate`, el certificado no
está en `/etc/letsencrypt/live/duran-ip/`: revisa `sudo certbot certificates` (¿se llama
`duran-ip`?). Para volver a tener el puerto 80 mientras lo arreglas: `NGINX_CONF=http` en `.env`
y `docker compose up -d nginx`.

### 16.5 "502 Bad Gateway" u Odoo no responde

1. `docker compose ps`: ¿odoo está `Up` o `Restarting`?
2. `docker compose logs --tail 100 odoo`: busca `ERROR` o `CRITICAL`.
3. Causas comunes:
   - **Falta `odoo.conf`**: Compose da un error de *bind source path does not exist* → paso 3.3.
   - **No conecta a PostgreSQL**: revisa `.env` y que `db` esté `healthy`.
   - **Recién recreado**: espera unos segundos; nginx vuelve a buscar la IP de Odoo cada 10 s.
4. Si sigue, `docker compose restart odoo nginx`.

### 16.6 El certificado no se renueva

**Dónde:** VM

```
systemctl list-timers | grep certbot
sudo journalctl -u snap.certbot.renew.service --since "3 days ago" | tail -30
sudo tail -50 /var/log/letsencrypt/letsencrypt.log
```

La causa más común es el puerto 80 cerrado (16.2) o nginx caído. Para renovar a mano en cuanto
se arregle: `sudo certbot renew`. Si el certificado se renovó pero nginx sigue mostrando el
viejo, el deploy-hook falló: `docker compose exec nginx nginx -s reload`.

⚠️ **Sin verificar:** el nombre exacto del servicio de systemd del snap
(`snap.certbot.renew.service`); `systemctl list-timers | grep certbot` muestra el nombre real.

### 16.7 La Master Password no funciona en el paso 6

- `grep '^list_db' odoo.conf` debe decir `True` durante el paso 6, y Odoo debe haberse recreado
  después (paso 6.2). Con `False`, Odoo registra "Database management functions blocked".
- `grep -c '^admin_passwd = \$pbkdf2-sha512\$' odoo.conf` debe dar `1`. Si te equivocaste de
  contraseña, genera otro hash (paso 3.3), cámbialo y recrea Odoo.

### 16.8 Los PDF salen sin estilo o los enlaces apuntan a otra dirección

Revisa los parámetros del paso 8 (Ajustes › Técnico › Parámetros del sistema).

### 16.9 Falla la restauración

- "la base … ya existe": elige otro nombre o borra la de prueba (14.7).
- Error de `pg_restore`: la base quedó a medias; bórrala (14.7, con su nombre) y revisa que el
  `.dump` sea el correcto (`head -c 5 <archivo.dump>` debe mostrar `PGDMP`).

### 16.10 Disco lleno

`df -h /` y `docker system df` (VM). Los logs de Docker ya están limitados (5 × 10 MB por
servicio). Los respaldos viejos se borran solos (quedan 14).

---

## 17. Lo que no está verificado

- **Firewall en otra VM:** el procedimiento de la sección 2 se verificó el 12-oct-2026 en
  esta VM; en otra puede cambiar (paso 2.8).
- **Si nginx en Docker necesita las reglas de INPUT** (paso 2.8): la prueba de 2.7 fue con un
  servidor fuera de Docker.
- **No usar `netfilter-persistent save`:** es una precaución, no un fallo observado (sección 2).
- **Quitar la regla del 8069** (paso 2.9): no se ha ejecutado.
- **Redacción exacta del `sed` (2.5) y de la prueba (2.7):** escrita después de lo hecho en la
  VM; el `sed` se probó sobre una copia de ejemplo de `rules.v4`.
- **Versión de Certbot del snap** en ARM64 el día de la instalación (paso 5.1).
- **Cambiar la IP del mismo certificado** sin borrarlo antes (paso 12).
- **Clonar un repo privado** con deploy key (paso 3.1).
- **cron en macOS** y sus permisos (paso 13.4).
- **Copia cifrada a Google Drive** con rclone (paso 13.5): solo documentada.
- **Restauración real en producción** (paso 14.8): el ensayo de la sección 14 es en la Mac.
- **Nombre del servicio de systemd** del snap de Certbot (paso 16.6).
- **"Instalar app" en el celular** con el certificado real: solo se puede probar en el celular
  (paso 11.7).

## 18. Fuentes

- Odoo 19, System configuration (deploy): workers, memoria, límites, proxy_mode, nginx y
  websocket, seguridad del gestor de bases —
  https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html
- Código de Odoo 19.0-20260908 (imagen fijada): `odoo/tools/config.py` (valores por defecto,
  `admin_passwd`, hash), `odoo/http.py` (proxy_mode y X-Forwarded-Host),
  `odoo/service/db.py` (`list_db` bloquea el gestor), `addons/base/models/res_users.py`
  (`web.base.url.freeze`), `addons/base/models/ir_actions_report.py` (`report.url`),
  `addons/bus/controllers/websocket.py` (`/websocket`, `/websocket/health`), `odoo/cli/neutralize.py`.
- Certbot, User Guide (`--ip-address`, `--preferred-profile`, `--deploy-hook`, renovación,
  webroot, staging) — https://eff-certbot.readthedocs.io/en/stable/using.html
- Certbot, CHANGELOG (5.3.0: `--ip-address` con standalone y manual; 5.4.0: webroot; umbral de
  1/2 para certificados de 10 días o menos) —
  https://github.com/certbot/certbot/blob/main/certbot/CHANGELOG.md
- Certbot, instrucciones de snap — https://certbot.eff.org/instructions?ws=other&os=snap
- Let's Encrypt, perfiles (shortlived: 160 h, admite IP) — https://letsencrypt.org/docs/profiles/
- nginx, WebSocket proxying — https://nginx.org/en/docs/http/websocket.html
- nginx, módulo upstream (`resolve`, `zone`) — https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- Docker, Packet filtering and firewalls — https://docs.docker.com/engine/network/packet-filtering-firewalls/
- Docker, Port publishing (loopback y Docker 28.0.0) — https://docs.docker.com/engine/network/port-publishing/
- Oracle, Best practices for Compute (no usar UFW en Ubuntu) —
  https://docs.oracle.com/en-us/iaas/Content/Compute/References/bestpracticescompute.htm
- Oracle, tutorial Apache en Ubuntu (iptables + `netfilter-persistent save`; esta guía **no**
  usa `netfilter-persistent save`, ver sección 2) —
  https://docs.oracle.com/en-us/iaas/developer-tutorials/tutorials/apache-on-ubuntu/01oci-ubuntu-apache-summary.htm
- Oracle, Public IP Addresses (efímera vs. reservada) —
  https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm
