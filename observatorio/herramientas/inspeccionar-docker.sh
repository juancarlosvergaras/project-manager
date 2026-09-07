#!/usr/bin/env bash
# Inspeccion de solo lectura de los contenedores y carpetas de las aplicaciones (OrbStack / Docker en macOS).
# No modifica nada. Redacta claves, secretos y tokens.
# Uso: bash inspeccionar-docker.sh
export PATH="$HOME/.orbstack/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
redactar() { sed -E 's/((PASS|PASSWORD|SECRET|KEY|TOKEN|CLAVE|CONTRASE|SALT|DATABASE_URL|MONGO_URI|DSN)[A-Za-z_]*\s*[=:]\s*)["'"'"']?[^"'"'"' ]+/\1[REDACTADO]/Ig'; }
sec() { printf '\n==================== %s ====================\n' "$1"; }

sec "CONTENEDORES"
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1

sec "DETALLE DE CADA CONTENEDOR (imagen, comando, carpetas montadas, variables redactadas)"
for c in $(docker ps -q 2>/dev/null); do
  echo "--- $(docker inspect -f '{{.Name}}' "$c")"
  docker inspect -f 'Imagen: {{.Config.Image}}
Comando: {{join .Config.Cmd " "}} | Entrypoint: {{join .Config.Entrypoint " "}}
Directorio: {{.Config.WorkingDir}}
Puertos: {{range $p, $b := .NetworkSettings.Ports}}{{$p}}->{{range $b}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}
Montajes: {{range .Mounts}}{{.Source}} => {{.Destination}} ; {{end}}
Compose: {{index .Config.Labels "com.docker.compose.project"}} / {{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$c" 2>/dev/null
  echo "Variables:"; docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null | redactar | sed 's/^/  /'
done

sec "CARPETA Servidor/apps"
ls -la "$HOME/Servidor/apps" 2>/dev/null
ls -la "$HOME/Servidor" 2>/dev/null

sec "MANIFIESTOS DE CADA APLICACION (primeras lineas, valores sensibles redactados)"
for d in "$HOME"/Servidor/apps/*/ "$HOME"/Servidor/*/; do
  [ -d "$d" ] || continue
  hay=0
  for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml Dockerfile package.json requirements.txt pyproject.toml manage.py composer.json go.mod; do
    if [ -f "$d$f" ]; then
      [ $hay = 0 ] && { echo; echo "##### $d"; ls "$d" | head -30; hay=1; }
      echo ">>> $f"; redactar < "$d$f" | head -45
    fi
  done
done

sec "TUNEL ACTIVO"
sudo -n cat /etc/cloudflared/config.yml 2>/dev/null || cat /etc/cloudflared/config.yml 2>/dev/null || echo "(sin permiso para leer /etc/cloudflared/config.yml; ejecute: sudo cat /etc/cloudflared/config.yml)"

sec "FIN"
echo "Revise el resultado antes de compartirlo."
