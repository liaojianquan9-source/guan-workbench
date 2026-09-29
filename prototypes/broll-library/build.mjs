import {build} from 'esbuild';
await build({entryPoints:['src/App.tsx'],bundle:true,outfile:'public/app.js',jsx:'automatic',format:'esm',minify:false,sourcemap:false,define:{'process.env.NODE_ENV':'"production"'},logLevel:'info'});
