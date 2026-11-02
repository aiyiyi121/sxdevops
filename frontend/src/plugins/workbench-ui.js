import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

export function installWorkbenchUi(app) {
    app.use(ElementPlus, { locale: zhCn })
    for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
        app.component(name, component)
    }
}
