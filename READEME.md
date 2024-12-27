#安装
执行root目录下的install.sh
cp config_exp.ini config.ini && cp resstart.sh-exp restart.sh && chmod 777 restart.sh &&  chmod 777 stop.sh
#运行
./restart.sh
#停止
./stop.sh