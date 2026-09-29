'use strict';
// The seven previews are bundled copies of real prototypes/broll-library shots.
// Keep IDs and replaceable-field labels aligned with that library's src/data.ts.
const AiMakingCatalog=[
 {id:'SHOT-001',name:'开头大字标题',type:'观点强调',poster:'case-001-title.jpg',video:'shot-001.mp4',duration:3.3,fields:['开头文字','参数标签','强调单字','右侧标题']},
 {id:'SHOT-002',name:'大数字参数展示',type:'数字说明',poster:'case-001-parameter.jpg',video:'shot-002.mp4',duration:2.43,fields:['主数字','数值单位','参数名称','英文标签与小注']},
 {id:'SHOT-003',name:'月球主题产品标题',type:'产品介绍',poster:'case-001-moon.jpg',video:'shot-003.mp4',duration:4.27,fields:['背景标题','产品名与型号','月球图片','文字纹理'],imageFields:['月球图片','文字纹理']},
 {id:'SHOT-004',name:'问题引入标题',type:'问题引入',poster:'case-002-problem.png',video:'shot-004.mp4',duration:2.53,fields:['主标题','上方文字','辅助英文','整张背景图'],imageFields:['整张背景图']},
 {id:'SHOT-005',name:'文章标题高亮',type:'证据引用',poster:'case-002-article.png',video:'shot-005.mp4',duration:3.23,fields:['文章标题与正文','高亮颜色','字体']},
 {id:'SHOT-006',name:'提示词输入演示',type:'步骤演示',poster:'case-002-prompt.png',video:'shot-006.mp4',duration:5.4,fields:['输入内容','卡片中的文字','无框文字','配色与光罩']},
 {id:'SHOT-007',name:'双列指标比较',type:'对比结论',poster:'case-002-comparison.png',video:'shot-007.mp4',duration:2.97,fields:['两列名称','平台与说明','得分与比例','脚注']},
];
if(typeof module!=='undefined')module.exports=AiMakingCatalog;
