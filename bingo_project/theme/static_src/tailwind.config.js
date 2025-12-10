/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */

module.exports = {
    content: [
        
        '../templates/**/*.html',
        '../../templates/**/*.html',
        '../../**/templates/**/*.html',

    ],
    theme: {
        extend: {
            fontFamily:  { 'sans': ['Inter', 'system-ui', 'sans-serif'] },
                    colors: {
                        'accent': {
                            50: '#f0f9ff', 100: '#e0f2fe', 200: '#bae6fd',
                            300: '#7dd3fc', 400: '#38bdf8', 500: '#0ea5e9',
                            600: '#0284c7', 700: '#0369a1',
                        }
                    }
                },
    },
    plugins: [
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/aspect-ratio'),
    ],
}
