from ada.web.branding.web import DEFAULT_OPERATIONAL_BRAND_LOGO_SRC
from atlanticus.web.index import IndexContribution

# El desbloqueo del scroll ocurre al terminar la transición de 500 ms.
# El fallback se dispara a los 14,5 segundos, aunque falten áreas.

# Índice de la aplicación: el loader se inyecta antes de montar Dash.
# La salida es por señales de primer render, con límite total de 15 segundos.
STARTUP_LOADER_INDEX = IndexContribution(
    body_start_fragments=(
        (
            '<div id="ada-io-startup-loader" class="ada-io-startup-loader" '
            'role="status" aria-label="Cargando operaciones">'
            '<img class="ada-io-startup-loader__logo" '
            f'src="{DEFAULT_OPERATIONAL_BRAND_LOGO_SRC}" alt="ADA">'
            '<p class="ada-io-startup-loader__subtitle">Asistente de Decisiones Ágiles</p>'
            '<div class="ada-io-startup-loader__waves" aria-hidden="true">'
            '<div></div><div></div></div></div>'
        ),
        (
            '<script>'
            '(function(){'
            'if(location.pathname!=="/"){'
            'document.documentElement.dataset.adaIoLoaderSkip="true";return;}'
            'document.documentElement.dataset.adaIoLoaderActive="true";'
            'var finished=false;'
            'window.adaIoFinishStartupLoader=function(reason){'
            'if(finished){return;}finished=true;'
            'if(reason==="timeout"){'
            'console.warn("[WARN] ADA startup loader timeout. Pending:",'
            'window.adaIoStartupPending?window.adaIoStartupPending():["unknown"]);}'
            'if(window.adaIoStopStartupObservers){window.adaIoStopStartupObservers();}'
            'var loader=document.getElementById("ada-io-startup-loader");'
            'if(loader){loader.classList.add("ada-io-startup-loader--exit");'
            'loader.setAttribute("aria-hidden","true");}'
            'window.setTimeout(function(){'
            'delete document.documentElement.dataset.adaIoLoaderActive;'
            'if(loader){loader.remove();}'
            'delete window.adaIoFinishStartupLoader;'
            'delete window.adaIoStartupPending;'
            'delete window.adaIoStopStartupObservers;'
            '},500);'
            '};'
            'window.setTimeout(function(){'
            'window.adaIoFinishStartupLoader("timeout");'
            '},14500);'
            '})();'
            '</script>'
        ),
    ),
)
