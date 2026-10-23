# 演示素材与许可

本仓库的简历示例全部为虚构，未使用真人照片、联系方式、公司履历或业务数据。`candidate@example.com` 为示例地址。

页头与分区符号由本项目脚本使用矢量路径绘制。没有打包外部纹理、图标字体或系统字体。

## 演示字体

公开演示 PDF 使用 Noto Sans SC 的静态实例，并按需嵌入字符子集。字体采用 SIL Open Font License 1.1，完整版权与条款保存在 [NotoSansSC-OFL.txt](licenses/NotoSansSC-OFL.txt)。源代码的 MIT 许可不替换字体许可。

- 来源：[Google Fonts / Noto Sans SC](https://github.com/google/fonts/tree/a85815a42757630ce188fdad368c2dfc444d4773/ofl/notosanssc)
- 输入字体：`NotoSansSC[wght].ttf`（可变字体）
- 源字体 SHA-256：`a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`
- 演示实例：使用 fontTools 把 `wght` 固定为400；字体文件仅用于本地构建，不包含在仓库或安装ZIP中

## 重建演示

先从上述固定来源取得字体及许可，保存在仓库外。安装开发依赖后执行：

```bash
fonttools varLib.instancer /path/to/NotoSansSC-VF.ttf wght=400 \
  --output /path/to/NotoSansSC-Regular.ttf

python skills/resume-rewrite/scripts/render_resume_pdf.py \
  --markdown examples/fictional-resume.md \
  --output docs/plain-demo.pdf --style plain \
  --font /path/to/NotoSansSC-Regular.ttf

python skills/resume-rewrite/scripts/render_resume_pdf.py \
  --markdown examples/fictional-resume.md \
  --output docs/classic-demo.pdf --style classic \
  --font /path/to/NotoSansSC-Regular.ttf

pdftoppm -scale-to 1500 -png -singlefile docs/plain-demo.pdf docs/plain-preview
pdftoppm -scale-to 1500 -png -singlefile docs/classic-demo.pdf docs/classic-preview
```

`pdftoppm` 来自 Poppler，用于把 PDF 渲染成整页 PNG。生成后应实际检查两张图片；字体变更可能改变换行和空间分配。
