import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        ink: '#07111c',
        slate: '#0f1a28',
        mist: '#8aa4c1',
        aqua: '#4ad7d1',
        ember: '#ff9d5c',
        rose: '#ff6b6b',
        lime: '#c7ff80'
      },
      boxShadow: {
        panel: '0 24px 70px rgba(2, 8, 23, 0.28)'
      },
      backgroundImage: {
        mesh:
          'radial-gradient(circle at top left, rgba(74, 215, 209, 0.22), transparent 28%), radial-gradient(circle at top right, rgba(255, 157, 92, 0.18), transparent 30%), linear-gradient(180deg, rgba(7, 17, 28, 0.96), rgba(10, 19, 31, 1))'
      }
    }
  },
  plugins: []
};

export default config;
