document.addEventListener('DOMContentLoaded', () => {
    
    // Configure HTMX to send JSON where appropriate (e.g. for PATCH requests)
    htmx.defineExtension('json-enc', {
        onEvent: function(name, evt) {
            if (name === "htmx:configRequest") {
                evt.detail.headers['Content-Type'] = "application/json";
            }
        },
        encodeParameters: function(xhr, parameters, elt) {
            xhr.overrideMimeType('text/json');
            return (JSON.stringify(parameters));
        }
    });

    // Handle generic HTMX errors
    document.body.addEventListener('htmx:responseError', function(event) {
        showToast('An error occurred during the request.', 'error');
    });

    // Handle HTMX successful responses that don't return HTML (e.g. 200 OK empty response)
    document.body.addEventListener('htmx:afterRequest', function(event) {
        if (event.detail.successful) {
            // Check if there's a custom header for toast messages
            const xhr = event.detail.xhr;
            const hxTrigger = xhr.getResponseHeader('HX-Trigger');
            
            if (hxTrigger) {
                try {
                    const triggers = JSON.parse(hxTrigger);
                    if (triggers.showMessage) {
                        showToast(triggers.showMessage.text, triggers.showMessage.type || 'success');
                    }
                } catch(e) {
                    // Not JSON or other error, ignore
                }
            }
        }
    });
});

// Programmatic way to show toasts if needed from JS
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toastHtml = `
        <div x-data="{ show: true }" x-init="setTimeout(() => show = false, 3000)" x-show="show" 
             x-transition:enter="transition ease-out duration-300" 
             x-transition:enter-start="opacity-0 transform translate-x-8" 
             x-transition:enter-end="opacity-100 transform translate-x-0" 
             x-transition:leave="transition ease-in duration-200" 
             x-transition:leave-start="opacity-100 transform translate-x-0" 
             x-transition:leave-end="opacity-0 transform translate-x-8" 
             class="flex items-center p-4 mb-4 text-sm rounded-lg shadow-lg pointer-events-auto border ${getTypeClasses(type)}"
             role="alert">
             <div>${message}</div>
             <button type="button" @click="show = false" class="ml-auto -mx-1.5 -my-1.5 p-1.5 rounded-lg focus:ring-2 focus:ring-gray-400 hover:bg-gray-700 inline-flex h-8 w-8 text-gray-400 hover:text-white transition-colors">
                <span class="sr-only">Close</span>
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg>
             </button>
        </div>
    `;
    
    // Create element and append
    const template = document.createElement('template');
    template.innerHTML = toastHtml.trim();
    container.appendChild(template.content.firstChild);
}

function getTypeClasses(type) {
    if (type === 'success') return 'text-green-400 bg-gray-800 border-green-800';
    if (type === 'error') return 'text-red-400 bg-gray-800 border-red-800';
    return 'text-blue-400 bg-gray-800 border-blue-800';
}
