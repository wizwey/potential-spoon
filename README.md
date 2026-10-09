# potential-spoon
针对安徽工业大学校园网每次需要操作联网的自动化脚本与程序
--------
首次使用：
1. 把 AHUT_WiFi_AutoLogin.exe 放到你想安装的文件夹（建议放在不容易被误删的位置，
   例如 D:\Tools\AHUT_WiFi）。

2. 双击运行 AHUT_WiFi_AutoLogin.exe。

3. 第一次运行会弹出配置窗口，填写：
   - WiFi 名称：通常填 AHUT-wifi6
   - 运营商：中国联通 / 中国移动 / 中国电信 / 校园网
   - 账号：校园网账号（学号）
   - 密码：校园网密码
   - 检测间隔 / 重试间隔：保持默认即可

4. 点击【保存并运行】后，程序会：
   - 在同级目录生成 .env 配置文件
   - 写入注册表“当前用户”的开机自启项
   - 隐藏窗口，在后台持续检测网络并自动登录

开机自启
--------
配置完成后会自动设置开机自启，无需额外操作。
写入的是 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run，
不需要管理员权限，只对当前登录用户生效。

停止运行
--------
打开任务管理器，结束名为 "AHUT_WiFi_AutoLogin.exe" 的进程即可。
