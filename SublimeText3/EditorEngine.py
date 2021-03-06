import sys, sublime, sublime_plugin, socket
from socketserver import TCPServer, StreamRequestHandler, ThreadingMixIn
from threading import Thread
import shlex, time, tempfile
import os.path
import pprint
import json
import subprocess
import getpass

class EditorEnginePluginHost(sublime_plugin.ApplicationCommand):
    def __init__ (self):
        self.__server = OIServer()
        self.__server.serve_forever()

    def __del__(self):
        self.__server.shutdown()

    def run(self):
        print("Not in use")

class OpenideEnvironmentShutdownCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        config_point = get_nearest_config_point(os.getcwd())
        if config_point != None:
            subprocess.Popen(["oi", "shutdown"], stderr=subprocess.STDOUT, cwd=config_point)

class OpenideEnvironmentStartCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        config_point = get_nearest_config_point(os.getcwd())
        if config_point != None:
            subprocess.Popen(["oi", "environment", "start"], stderr=subprocess.STDOUT, cwd=config_point)

class TypeSearchWindowCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        send_editor_engine_message("gototype")

class ExplorerWindowCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        send_editor_engine_message("explore")

class GoToAutoTestNetCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        send_editor_engine_message("autotest.net setfocus")

class OpenIdeRunCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        send_editor_engine_message("run")

class BufferChangeEvent(sublime_plugin.EventListener):
    def on_modified(self, view):
        if view.file_name() == None:
            return
        msg = "editor buffer-changed " + view.file_name()
        sublime.set_timeout(lambda: send_editor_engine_message_from_view(view, msg), 5)

class OpenIdeDispatchCommand(sublime_plugin.ApplicationCommand):
    def run(self, message):
        send_editor_engine_message(message)

class OpenIdeLanguageCommandCommand(sublime_plugin.WindowCommand):
    def run(self, message):
        view = self.window.active_view()
        engine_message = 'none command '+message
        if not view == None:
            if not view.file_name() == None:
                filename, extension = os.path.splitext(view.file_name())
                if len(extension) > 0:
                    engine_message = extension+' command '+message
        send_editor_engine_message(engine_message)

class OpenIdeInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit, filename, line, column, text):
        point = get_point(filename, line, column)
        print(sublime.active_window().active_view().file_name())
        print(filename) 
        if sublime.active_window().active_view().file_name() != filename:
            sublime.set_timeout(lambda: open_point(point), 5)
            view = go_to_file(point.File)
            if view == None:
                return
            time_slept = 0
            while view.is_loading():
                if time_slept > 1:
                    break;
                time.sleep(0.05)
                time_slept += 0.05
        else:
            view = sublime.active_window().active_view()
        view.insert(edit, view.text_point(point.Line, point.Column), text)

class OpenIdeRemoveCommand(sublime_plugin.TextCommand):
    def run(self, edit, filename, lineStart, columnStart, lineEnd, columnEnd):
        start = get_point(filename, lineStart, columnStart)
        end = get_point(filename, lineEnd, columnEnd)
        if sublime.active_window().active_view().file_name() != filename:
            sublime.set_timeout(lambda: open_point(start), 5)
            time.sleep(0.15)
            view = go_to_file(start.File)
            if view == None:
                return
            time_slept = 0
            while view.is_loading():
                if time_slept > 1:
                    break;
                time.sleep(0.05)
                time_slept += 0.05
        else:
            view = sublime.active_window().active_view()
        start_point=view.text_point(start.Line, start.Column)
        end_point=view.text_point(end.Line, end.Column)
        view.erase(edit, sublime.Region(start_point, end_point))

class ProjectLoadHandler(sublime_plugin.EventListener):
    last_loaded = None

    def on_activated_async(self, view):
        if view.file_name() == None:
            return
        token = get_editor_engine_token(view.file_name())
        if token == None:
            return
        lastpath, _ = token
        if not view.file_name().startswith(lastpath):
            return
        if self.last_loaded == lastpath:
            return
        project = sublime.active_window().project_file_name()
        if not project == None:
            data = sublime.active_window().project_data()
            if len(data['folders']) > 0:
                path, _ = token
                for folder in data['folders']:
                    if folder['path'] == path:
                        pass

        #if os.path.exists(path):
        #    lines = runProcess(['oi', 'conf', 'read', 'editor.sublime.project'], path)
        #    if len(lines) == 1:
        #        project = os.path.join(path, lines[0])
        #        self.last_loaded = path
        #        runProcess(['oi', 'editor', 'command', 'load-project', project], path)

###########################################################################
####################################### Commands ##########################

def handle_command(cmd):
    command = cmd.decode('UTF-8')
    if len(command) == 0:
        return None
    args = shlex.split(command)
    if args[0] == "ping":
        return "pong"
    if args[0] == "goto":
        open_file(args)
    if args[0] == "can-insert-for":
        return "true"
    if args[0] == "can-remove-for":
        return "true"
    if args[0] == "insert":
        insert(args)
    if args[0] == "remove":
        remove(args)
    if args[0] == "get-dirty-buffers":
        return get_dirty_buffers()
    if args[0] == "get-buffer-content":
        return get_buffer_content(args)
    if args[0] == "caret":
        return get_caret(args)
    if args[0] == "user-select":
        select_item(args)
    if args[0] == "user-select-at-caret":
        select_item_at_caret(args)
    if args[0] == "user-input":
        input_item(args)
    if args[0] == "get-windows":
        return get_windows(args)
    return None

def open_file(args):
    point = get_point(args[1], args[2], args[3])
    window = sublime.active_window().active_group()
    if len(args) == 5:
        window = int(args[4])-1
    sublime.set_timeout(lambda: open_point(point, window), 5)

def insert(args):
    text = args[1].replace("||newline||", os.linesep)
    if sublime.active_window().active_view().file_name() != args[2]:
        open_file(["", args[2],args[3],args[4]])
    def run_insert_command(filename, line, column, text):
        sublime.active_window().run_command('open_ide_insert', {"filename": filename, "line": line, "column": column, "text": text})
    if sublime.active_window().active_view().file_name() != args[2]:
        sublime.set_timeout(lambda: run_insert_command(args[2],args[3],args[4],text), 300)
    else:
        sublime.set_timeout(lambda: run_insert_command(args[2],args[3],args[4],text), 0)

def remove(args):
    sublime.active_window().run_command('open_ide_remove', {"filename": args[1], "lineStart": args[2], "columnStart": args[3], "lineEnd": args[4], "columnEnd": args[5]})

def get_dirty_buffers():
    dirty_buffers = DirtyBufferFinder()
    return dirty_buffers.get()

def get_buffer_content(args):
    content_reader = BufferContent()
    return content_reader.get(args[1])

def get_caret(args):
    view = sublime.active_window().active_view()
    if view == None:
        return "untitled|1|1"
    line, column = view.rowcol(view.sel()[0].begin())
    filename = view.file_name()
    return filename+"|"+str(line+1)+"|"+str(column+1)

def select_item(args):
    items = []
    keys = []
    for item in args[2].split(','):
        chunks = item.split("||")
        if len(chunks) > 1:
            keys.append(chunks[0])
            items.append(chunks[1])
        else:
            keys.append(item)
            items.append(item)

    def on_done(e):
        response = "user-cancelled"
        if e != -1:
            response = keys[e]
        msg = "user-selected \"" + args[1] + "\" \""  + response + "\""
        sublime.set_timeout(lambda: send_editor_engine_message_from_view(window.active_view(), msg), 5)
    window = sublime.active_window()
    window.show_quick_panel(items, on_done)

def select_item_at_caret(args):
    items = []
    keys = []
    for item in args[2].split(','):
        chunks = item.split("||")
        if len(chunks) > 1:
            keys.append(chunks[0])
            items.append(chunks[1])
        else:
            keys.append(item)
            items.append(item)

    def on_done(e):
        response = "user-cancelled"
        if e != -1:
            response = keys[e]
        msg = "user-selected-at-caret \"" + args[1] + "\" \""  + response + "\""
        sublime.set_timeout(lambda: send_editor_engine_message_from_view(sublime.active_window().active_view(), msg), 5)
    view = sublime.active_window().active_view()
    view.show_popup_menu(items, on_done)

def input_item(args):
    def on_done(e):
        msg = "user-inputted \"" + args[1] + "\" \""  + e + "\""
        sublime.set_timeout(lambda: send_editor_engine_message_from_view(window.active_view(), msg), 5)

    def on_cancel():
        msg = "user-inputted \"" + args[1] + "\" \"user-cancelled\""
        sublime.set_timeout(lambda: send_editor_engine_message_from_view(window.active_view(), msg), 5)
    
    window = sublime.active_window()
    window.show_input_panel("Input", args[2], on_done, None, on_cancel)

def get_windows(args):
    window_str = ""
    windows = sublime.windows()
    active = sublime.active_window().active_group()+1
    for window in windows:
        for group in range(1, window.num_groups() + 1):
            window_str = window_str + str(group) + "|"
    return str(active)+"|"+window_str.strip("|")

###########################################################################
####################################### Editor Engine Client ##############
def send_editor_engine_message(message):
    sublime.set_timeout(lambda: marshal_editor_engine_message(message), 5)

def marshal_editor_engine_message(message):
    view = sublime.active_window().active_view()
    send_editor_engine_message_from_view(view, message)

def send_editor_engine_message_from_view(view,message):
    client = get_editor_engine_client(view)
    if client == None:
        return
    send_to_editor_engine(client, message)

def send_to_editor_engine(client,message):
    sock = get_editor_engine_socket_client(client)
    sock.sendall(bytes(message + "\x00", 'UTF-8'))
    sock.close()

def get_editor_engine_socket_client(client):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", client[1]))
    return sock

def get_editor_engine_client(view):
    if view == None:
        token = get_editor_engine_token(None)
    else:
        file_name = view.file_name()
        token = get_editor_engine_token(file_name)
    if token == None:
        return None
    return token

def is_same_as_engine(running, suggested):
    return running == suggested or suggested.startswith(running+os.sep)

def get_nearest_config_point(file_name):
    path = file_name
    while True:
        if path == os.path.dirname(path) :
            break
        path = os.path.dirname(path) 
        config_point = os.path.join(path, ".OpenIDE")
        if os.path.exists(config_point):
            return path;
    return None

def get_editor_engine_token(file_name):
    tempdir = tempfile.gettempdir()
    if sys.platform == "darwin":
        tempdir = "/tmp"
    editor_token_path = tempdir
    engines = []
    if os.path.exists(editor_token_path) == True:
        all_engines = []
        path_ending = ".EditorEngine."+getpass.getuser()+".pid"
        for pid_file_name in os.listdir(editor_token_path):
            pid_file = os.path.join(editor_token_path, pid_file_name)
            if pid_file.endswith(path_ending):
                client = get_editor_engine_client_settings(pid_file)
                if client != None:
                    all_engines.append(client)
                    if file_name != None:
                        if is_same_as_engine(client[0], file_name):
                            engines.append(client)
        if len(engines) == 0 and len(all_engines) > 0:
            return all_engines[0]
    return get_nearest_token(engines)

def get_nearest_token(engines):
    if len(engines) == 0:
        return None
    closest_client = None
    for client in engines:
        if closest_client == None:
            closest_client = client
            continue

        if len(client[0]) > len(closest_client[0]):
            closest_client = client
    return closest_client

def get_editor_engine_client_settings(pid_file):
    try:
        with open(pid_file) as f:
            lines = f.readlines()
            if len(lines) != 2:
                return None
            client = []
            client.append(lines[0].replace("\n", ""))
            client.append(int(lines[1].replace("\n", "")))
            sock = get_editor_engine_socket_client(client)
            sock.close()
            return client
    except:
        os.remove(pid_file)
        return None
    return None

###########################################################################
####################################### TCP Server ########################

class TCPThreadedServer(TCPServer, ThreadingMixIn):
    class RequstHandler(StreamRequestHandler):
        def handle(self):
            msg = self.rfile.readline().strip()
            reply = self.server.process(msg)
            if reply is not None:
                self.wfile.write(bytes(reply + '\n', 'UTF-8'))

    def __init__(self, host, port, name=None):
        self.allow_reuse_address = True
        TCPServer.__init__(self, (host, port), self.RequstHandler)
        if name is None: name = "%s:%s" % (host, port)
        self.name = name
        self.poll_interval = 0.5

    def process(self, msg):
        raise NotImplemented

    def serve_forever(self, poll_interval=0.5):
        self.poll_interval = poll_interval
        self.trd = Thread(target=TCPServer.serve_forever,
                        args = [self, self.poll_interval],
                        name = "PyServer-" + self.name)
        self.trd.start()

    def shutdown(self):
        TCPServer.shutdown(self)
        TCPServer.server_close(self)
        self.trd.join()
        del self.trd

class OIServer(TCPThreadedServer):
    def __init__(self):
        TCPThreadedServer.__init__(self, "localhost", 9998, "Server")

    def process(self, data):
        reply = None
        if data is not None:
            reply = handle_command(data)
        return reply

###########################################################################
####################################### Core Stuff ########################

def runProcess(exe,workingDir=""):    
    if workingDir == "":
        workingDir = os.getcwd()
    p = subprocess.Popen(exe, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=workingDir)
    lines = []
    while(True):
        retcode = p.poll() # returns None while subprocess is running
        line = p.stdout.readline().decode(encoding='windows-1252').strip('\n').strip('\r')
        if line != "":
            lines.append(line)
        if(retcode is not None):
            break
    return lines

def open_point(point, groupid):
    if sublime.active_window().active_group() != groupid:
        sublime.active_window().focus_group(groupid)
    view = go_to_file_position(point.File, point.Line, point.Column)
    if view == None:
        return
    go_to_position(view, point)
    sublime.active_window().focus_view(view)

class DirtyBufferFinder:
    def get(self):
        self.completed = False
        sublime.set_timeout(lambda: self.add_dirty_buffers(), 5)
        while self.completed == False:
            time.sleep(0.1)
        return self.dirty_buffers

    def add_dirty_buffers(self):
        self.dirty_buffers = ""
        windows = sublime.windows()
        for window in windows:
            views = window.views()
            for view in views:
                if view.is_dirty():
                    self.dirty_buffers += view.file_name() + "|"
        self.completed = True

class BufferContent:
    def get(self, file_name):
        self.completed = False
        sublime.set_timeout(lambda: self.get_content(file_name), 5)
        while self.completed == False:
            time.sleep(0.1)
        return self.content.replace("\n", "||newline||")

    def get_content(self, file_name):
        self.content = ""
        view = get_view(file_name)
        if view.file_name() == file_name:
            self.content = view.substr(sublime.Region(0, view.size()))
        self.completed = True

def get_view(file_name):
    windows = sublime.windows()
    for window in windows:
        views = window.views()
        for view in views:
            if view.file_name() == file_name:
                return view
    return None

def go_to_file(file_name):
    if os.path.exists(file_name) == False:
        return None
    window = sublime.active_window()
    return window.open_file(file_name)

def go_to_file_position(file_name,line,column):
    if os.path.exists(file_name) == False:
        return None
    window = sublime.active_window()
    position = ":" + str(line) + ":" + str(column)
    return window.open_file(file_name + position, sublime.ENCODED_POSITION)

def go_to_position(view, point):
    sublime_point = view.text_point(point.Line, point.Column)
    view.sel().clear()
    view.sel().add(sublime.Region(sublime_point))
    return view

def get_point(file, line, column):
    return Point(file, line, column)

class Point():
    def __init__(self,file,line,column):
        self.File=file
        self.Line=int(line)-1
        self.Column=int(column)-1

def log(text):
    print(text)
    #with open("/tmp/test.txt", "a") as myfile:
        #myfile.write(text + "\n")
