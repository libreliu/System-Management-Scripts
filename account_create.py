import errno
import csv
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import random
import string
import argparse
import configparser
import os
import pty

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


from email.utils import formataddr

def send_email(to_addr, subject, content):
    """通过SSL发送HTML邮件"""
    msg = MIMEMultipart()
    
    from_addr = formataddr((config['EMAIL']['FromName'], config['EMAIL']['FromAddr']))
    to_addr = formataddr((to_addr, to_addr))
    
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = Header(subject, 'utf-8')

    msg.attach(MIMEText(content, 'html', 'utf-8'))

    with smtplib.SMTP_SSL(config['EMAIL']['SmtpServer'], config['EMAIL']['SmtpPort']) as server:
        server.login(config['EMAIL']['SmtpUser'], config['EMAIL']['SmtpPass'])
        server.sendmail(config['EMAIL']['FromAddr'], to_addr, msg.as_string())

        
def main(csv_path, config_path, force=False):
    global config
    config = get_config(config_path)
    
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # 跳过表头行

        for row in reader:
            fullname = row[0].strip()
            username = row[1].strip()
            email = row[2].strip()
            
            if not all([fullname, username, email]):
                print(f'Invalid record: {row}, skipped.')
                continue
            
            password = generate_password()
            create_user(username, password, force)
            
            if user_exists(username):
                secret_key, ga_output = setup_2fa(username)
                
                # 将二维码部分用<pre>标签和等宽字体包裹
                qrcode_html = f'<pre style="font-family: Consolas, Monaco, monospace;">{ga_output}</pre>'
                
                content = config['EMAIL']['Template'].format(
                    system_name=config['SYSTEM']['Name'],
                    fullname=fullname,
                    username=username,
                    password=password,
                    secret_key=secret_key,
                    qrcode=qrcode_html
                )
                
                subject = f'{config["SYSTEM"]["Name"]} System User Modification'
                send_email(email, subject, content)
                
                print(f'User {username} created/updated successfully.')
                print(f'Username: {username}')
                print(f'Password: {password}')
                print(f'Secret Key: {secret_key}')
                print()
            else:
                print(f'Failed to create user {username}.')

def get_config(config_path):
    """读取配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def generate_password(length=12):
    """生成随机密码"""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(random.choice(chars) for _ in range(length))

def create_user(username, password, force=False):
    """创建Linux系统账号"""
    if not user_exists(username):
        cmd = f'sudo adduser --disabled-password --gecos "" {username}'
        subprocess.run(cmd, shell=True, check=True)
    elif force:
        print(f'User {username} already exists, password will be updated.')
    else:
        print(f'User {username} already exists, skipped.')
        return
    
    cmd = f'echo "{username}:{password}" | sudo chpasswd'
    subprocess.run(cmd, shell=True, check=True)

def setup_2fa(username):
    """设置账号2FA"""
    m, s = pty.openpty()
    p = subprocess.Popen(['sudo', '-u', username, 'google-authenticator', '-Q', 'utf8', '-t', '-d', '-f', '-r', '3', '-R', '30', '-w', '3'], 
                         stdin=subprocess.PIPE, stdout=s, stderr=s, close_fds=True)
    os.close(s)
    os.write(p.stdin.fileno(), b'\n\n\n\n\n\n\ny\n')
    
    output = b''
    while True:
        try:
            data = os.read(m, 1024)
        except OSError as e:
            if e.errno != errno.EIO:
                raise
            break  # EIO means EOF on some systems
        else:
            if not data:  # EOF
                break
        output += data
    
    os.close(m)    
    p.wait()
    output = output.decode()
    
    secret_key = output.split('\n')[0].replace('Your new secret key is: ', '')
    return secret_key, output

def user_exists(username):
    """检查Linux账号是否已存在"""
    cmd = f'id {username}'
    return subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL).returncode == 0
        

        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('csv_path', help='The path of csv file')
    parser.add_argument('config_path', help='The path of config file')
    parser.add_argument('-f', '--force', action='store_true', 
                        help='Force update password if user already exists')
    
    args = parser.parse_args()
    main(args.csv_path, args.config_path, args.force)

