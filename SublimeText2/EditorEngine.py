import sublime, sublime_plugin, socket
from SocketServer import TCPServer, StreamRequestHandler, ThreadingMixIn
from threading import Thread
import shlex, time, tempfile
import os.path

class EditorEnginePluginHost(sublime_plugin.ApplicationCommand):
	def __init__ (self):
		self.__server = OIServer()
		self.__server.serve_forever()

	def __del__(self):
		self.__server.shutdown()

	def run(self):
		print "Not in use"

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

###########################################################################
####################################### Commands ##########################

def handle_command(command):
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
	return None

def open_file(args):
	point = get_point(args[1], args[2], args[3])
	sublime.set_timeout(lambda: open_point(point), 5)

def insert(args):
	text = args[1]
	point = get_point(args[2], args[3], args[4])
	sublime.set_timeout(lambda: insert_at(point, text), 5)

def remove(args):
	start = get_point(args[1], args[2], args[3])
	end = get_point(args[1], args[4], args[5])
	sublime.set_timeout(lambda: remove_at(start, end), 5)

def get_dirty_buffers():
	dirty_buffers = DirtyBufferFinder()
	return dirty_buffers.get()

def get_buffer_content(args):
	content_reader = BufferContent()
	return content_reader.get(args[1])

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
	sock.sendall(message + "\x00")
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

def get_editor_engine_token(file_name):
	editor_token_path = os.path.join(tempfile.gettempdir(), "EditorEngine")
	engines = []
	if os.path.exists(editor_token_path) == True:
		all_engines = []
		for pid_file_name in os.listdir(editor_token_path):
			pid_file = os.path.join(editor_token_path, pid_file_name)
			if pid_file.endswith(".pid"):
				client = get_editor_engine_client_settings(pid_file)
				if client != None:
					all_engines.append(client)
					if file_name != None:
						if file_name.startswith(client[0]):
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
				self.wfile.write(str(reply) + '\n')

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

def open_point(point):
	view = go_to_file_position(point.File, point.Line, point.Column)
	if view == None:
		return
	go_to_position(view, point)
	sublime.active_window().focus_view(view)

def insert_at(point, text):
	view = go_to_file(point.File)
	if view == None:
		return
	while view.is_loading():
		time.sleep(0.05)
	edit = view.begin_edit()
	view.insert(edit, view.text_point(point.Line, point.Column), text)
	view.end_edit(edit)

def remove_at(start, end):
	view = go_to_file(start.File)
	if view == None:
		return
	while view.is_loading():
		time.sleep(0.05)
	edit = view.begin_edit()
	start_point=view.text_point(start.Line, start.Column)
	end_point=view.text_point(end.Line, end.Column)
	view.erase(edit, sublime.Region(start_point, end_point))
	view.end_edit(edit)

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
	print text
	#with open("/tmp/test.txt", "a") as myfile:
		#myfile.write(text + "\n")
