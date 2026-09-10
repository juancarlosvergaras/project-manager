# Conversión de los formularios Laravel a definiciones del módulo de cuestionarios

Scripts con los que se convirtieron los tres formularios de unicartagena.edu.co (`curl -sL` de la página a un .html) a los JSON de `portal/src/ejemplos/`:

1. `extraer.py pagina.html` vuelca la estructura para revisarla.
2. `convertir.py pagina.html clave > def.json` produce la definición.
3. `finalizar.py` aplica los retoques de cada ejemplo (dimensiones, cálculo, duplicados, tablero) y los deja en `src/ejemplos/`; ajuste la ruta `DESTINO` a su copia del repositorio.
4. `resumir.py def.json` imprime la definición en una línea por bloque.
