from ada.web.branding.web import DEFAULT_OPERATIONAL_BRAND_LOGO_SRC
from atlanticus.web.index import IndexContribution

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
            'var finished=false;var timeoutId=null;'
            'window.adaIoFinishStartupLoader=function(reason){'
            'if(finished){return;}finished=true;'
            'if(timeoutId!==null){window.clearTimeout(timeoutId);timeoutId=null;}'
            'if(reason==="timeout"){'
            'console.warn("[WARN] ADA startup loader timeout");}'
            'if(window.adaIoStopStartupObservers){window.adaIoStopStartupObservers();}'
            'var loader=document.getElementById("ada-io-startup-loader");'
            'if(loader){loader.classList.add("ada-io-startup-loader--exit");'
            'loader.setAttribute("aria-hidden","true");}'
            'window.setTimeout(function(){'
            'delete document.documentElement.dataset.adaIoLoaderActive;'
            'if(loader){loader.remove();}'
            'delete window.adaIoFinishStartupLoader;'
            'delete window.adaIoStopStartupObservers;'
            '},500);'
            '};'
            'timeoutId=window.setTimeout(function(){'
            'if(typeof window.adaIoFinishStartupLoader==="function"){'
            'window.adaIoFinishStartupLoader("timeout");}'
            '},14500);'
            '})();'
            '</script>'
        ),
    ),
)
