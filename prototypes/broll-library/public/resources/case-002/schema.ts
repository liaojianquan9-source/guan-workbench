import {z} from 'zod';

export const casePropsSchema = z.object({
  motionEnabled: z.boolean().default(false),
  sceneId: z.string().default('auto'),
  content: z.record(z.string(), z.string()).default({}),
  numbers: z.record(z.string(), z.union([z.number(), z.string()])).default({}),
  assets: z.record(z.string(), z.string()).default({}),
  fonts: z.record(z.string(), z.string()).default({}),
  colors: z.record(z.string(), z.string()).default({}),
  light: z.record(z.string(),z.object({centerX:z.number(),centerY:z.number(),radiusX:z.number().positive(),radiusY:z.number().positive()})).default({}),
  theme: z.object({
    articleBackground: z.string().default('#06121e'),
    greenBackground: z.string().default('#071b06'),
    paper: z.string().default('#efe1ae'),
    ink: z.string().default('#f0f3e9'),
    accent: z.string().default('#a4e49a'),
    positive: z.string().default('#6cf656'),
    negative: z.string().default('#ff4e47'),
    metalLight: z.string().default('#f2f5fa'),
    metalDark: z.string().default('#b7b7b4'),
    secondaryInk: z.string().default('#bcbac2'),
  }).default({articleBackground:'#06121e',greenBackground:'#071b06',paper:'#efe1ae',ink:'#f0f3e9',accent:'#a4e49a',positive:'#6cf656',negative:'#ff4e47',metalLight:'#f2f5fa',metalDark:'#b7b7b4',secondaryInk:'#bcbac2'}),
});
export type CaseProps = z.infer<typeof casePropsSchema>;
