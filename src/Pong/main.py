# author:
# created at:
# company/institute:


# you can import all packages that come with SweepMe!

# removed unused imports

# you can import any module that is shipped with SweepMe!, see credits.html
# Any other module must be put into the folder of your function and loaded by
# adding the path the python environment using the following two lines:
from pysweepme import FolderManager as FoMa
import random
import math

FoMa.addFolderToPATH()


class Main():

    # please define variables and units as returned by the function 'main'
    variables = ["Player 1 Score", "Player 2 Score"]
    units = ["", ""]

    # here we can define the arguments presented in the user interface that are later handed over to function 'main'
    # the keys are the argument names, the values are the default values for the user interface
    arguments = {
        "Ball speed": "5.0",  # a float let you insert an float
        "Paddle 1 size": "10",  # an integer let you insert an integer
        "Paddle 2 size": "10",  # an integer let you insert an integer
    }

    def __init__(self):
        # keep last known values so Main.main can return something even if widget is not present
        self.ball_speed = float(self.arguments["Ball speed"])
        self.paddle1_size = 50
        self.paddle2_size = 50
        self.player1_score = 0
        self.player2_score = 0
        self.widget = None

    def configure(self):
        # set the score to 0 0
        self.widget.player1_score = 0  # bottom paddle
        self.widget.player2_score = 0  # top paddle

    ## Attention: this function is called in the main GUI thread so that the widget is automatically
    ## created in the correct thread
    def renew_widget(self, widget=None):
        """ gets the widget from the module and returns the same widget or creates a new one"""

        if widget is None:
            # if the widget has not been created so far, we create it now and store it as self.widget
            self.widget = PongWidget()
        else:
            # the second time a run is started, we can use the widget that is handed over to 'renew_widget'
            # to store it as self.widget
            self.widget = widget

        # attach a callback so the widget can notify Main after scoring
        try:
            self.widget.score_callback = self.main
        except Exception:
            # widget might not expose attribute in some contexts; ignore silently
            pass

        # return the widget to inform the module which one has to be inserted Widget into the Dashboard
        return self.widget

    def main(self, **kwargs):
        """
        This function is called by the host. Whenever it is called we update the stored
        runtime parameters (Ball speed, Paddle size) if provided and apply them to the
        live widget immediately. Always return the current scores.

        Returns: (player1_score, player2_score)
        """
        # update from kwargs for runtime parameters if provided
        new_ball_speed = float(kwargs.get("Ball speed", "1"))
        paddle_1_size = kwargs.get("Paddle 1 size", self.paddle1_size)
        if paddle_1_size is not None:
            self.paddle1_size = int(float(paddle_1_size))

        paddle_2_size = kwargs.get("Paddle 2 size", self.paddle2_size)
        if paddle_2_size is not None:
            self.paddle2_size = int(float(paddle_2_size))
        if new_ball_speed is not None:
            try:
                self.ball_speed = float(new_ball_speed)
            except Exception:
                pass

        # if we have a live widget, apply runtime updates immediately
        if getattr(self, 'widget', None) is not None:
            try:
                w = self.widget
                # apply speed update: preserve direction signs, change magnitude
                if new_ball_speed is not None:
                    try:
                        sx = 1 if w.ball_dx >= 0 else -1
                        sy = 1 if w.ball_dy >= 0 else -1
                        w.ball_dx = sx * float(self.ball_speed)
                        w.ball_dy = sy * float(self.ball_speed)
                        w._initial_speed = float(self.ball_speed)
                    except Exception:
                        pass
                # apply paddle size update: set widths and recenter horizontally
                try:
                    w.paddle_width = int(self.paddle1_size)
                    w.paddle2_width = int(self.paddle2_size)
                    ww = w.width()
                    # w.paddle_x = (ww - w.paddle_width) // 2
                    # w.paddle2_x = (ww - w.paddle2_width) // 2
                except Exception:
                    pass
                # keep stored scores in sync with widget
                try:
                    self.player1_score = int(getattr(w, 'player1_score', self.player1_score))
                except Exception:
                    pass
                try:
                    self.player2_score = int(getattr(w, 'player2_score', self.player2_score))
                except Exception:
                    pass
            except Exception:
                pass

        # always return the current scores
        return self.player1_score, self.player2_score


from PySide2.QtWidgets import QWidget
from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QPainter, QColor

class PongWidget(QWidget):
    def __init__(self, speed=2.0, paddle_size=120):
        super().__init__()
        self.setWindowTitle("Mini-Pong")
        self.setGeometry(100, 100, 800, 600)

        # runtime initialization guard - positions are set in showEvent when widget has a real size
        self._initialized = False

        # store configurable parameters
        self._initial_speed = speed
        self._initial_paddle_size = paddle_size

        # defaults (will be overwritten in showEvent)
        self.ball_radius = 10
        self.ball_x = 0
        self.ball_y = 0
        self.ball_dx = speed
        self.ball_dy = -abs(speed)

        # Bottom paddle (Player 1)
        self.paddle_width = paddle_size
        self.paddle_height = 10
        self.paddle_x = 0
        self.paddle_y = 0

        # Top paddle (Player 2)
        self.paddle2_width = paddle_size
        self.paddle2_height = 10
        self.paddle2_x = 0
        self.paddle2_y = 0

        # Scores
        self.player1_score = 0  # bottom paddle
        self.player2_score = 0  # top paddle

        # spawn center (where the ball resets)
        self.spawn_x = 0
        self.spawn_y = 0

        # pressed keys state (allows simultaneous presses)
        self.pressed_keys = set()

        # Timer for the game
        self.timer = QTimer()
        self.timer.timeout.connect(self.game_loop)
        self.timer.start(16)  # ~60 FPS

        self.setFocusPolicy(Qt.StrongFocus)

    def apply_updates_and_resume(self, new_speed=None, new_paddle=None):
        """Apply runtime updates (speed, paddle size) and resume the game if it was paused for scoring."""
        try:
            if new_speed is not None:
                # preserve current direction signs but set magnitude to new_speed
                sx = 1 if self.ball_dx >= 0 else -1
                sy = 1 if self.ball_dy >= 0 else -1
                self.ball_dx = sx * float(new_speed)
                self.ball_dy = sy * float(new_speed)
                self._initial_speed = float(new_speed)
            if new_paddle is not None:
                self.paddle_width = int(new_paddle)
                self.paddle2_width = int(new_paddle)
                ww = self.width()
                # recenter paddles
                self.paddle_x = (ww - self.paddle_width) // 2
                self.paddle2_x = (ww - self.paddle2_width) // 2
        except Exception:
            pass
        # clear waiting flag and restart timer
        self.waiting_for_resume = False
        # ensure ball is correctly placed (keep the spawn reset state)
        # restart timer
        try:
            self.timer.start(16)
        except Exception:
            pass

    def showEvent(self, event):
        # initialize positions once we have a valid size
        if not self._initialized:
            w, h = self.width(), self.height()

            # Paddle-Position (place near bottom)
            self.paddle_width = self._initial_paddle_size
            self.paddle_x = (w - self.paddle_width) // 2
            self.paddle_y = h - 40  # 40 px above bottom

            # Top paddle (place near top)
            self.paddle2_width = self._initial_paddle_size
            self.paddle2_x = (w - self.paddle2_width) // 2
            self.paddle2_y = 20

            # spawn center (center of the widget)
            self.spawn_x = w // 2
            self.spawn_y = h // 2

            # Ball: place at spawn center
            self.ball_radius = 10
            self.ball_x = self.spawn_x
            self.ball_y = self.spawn_y
            # choose initial direction randomly (up or down)
            self._reset_ball(toward_up=random.choice([True, False]))

            self._initialized = True
        super().showEvent(event)

    def resizeEvent(self, event):
        # when the window is resized, recenter paddles and update spawn center
        w, h = self.width(), self.height()
        # center paddles horizontally
        self.paddle_x = (w - self.paddle_width) // 2
        self.paddle2_x = (w - self.paddle2_width) // 2
        # keep paddles at same vertical offset from edges
        self.paddle_y = h - 40
        self.paddle2_y = 20
        # update spawn center
        self.spawn_x = w // 2
        self.spawn_y = h // 2
        # do not forcibly move the ball mid-game; only update spawn center used for resets
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Background
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        # Ball (draw from center)
        painter.setBrush(QColor(255, 255, 255))
        r = self.ball_radius
        painter.drawEllipse(self.ball_x - r, self.ball_y - r, r * 2, r * 2)
        # Bottom paddle (Player 1)
        painter.drawRect(self.paddle_x, self.paddle_y, self.paddle_width, self.paddle_height)
        # Top paddle (Player 2)
        painter.drawRect(self.paddle2_x, self.paddle2_y, self.paddle2_width, self.paddle2_height)
        # Draw scores
        painter.setPen(QColor(255, 255, 255))
        # bottom player score at bottom-left, top player score at top-left
        painter.drawText(10, self.height() - 10, f"P1: {self.player1_score}")
        painter.drawText(10, 20 + 10, f"P2: {self.player2_score}")

    def keyPressEvent(self, event):
        # track key down; ignore auto-repeat events because we handle continuous movement in the timer
        try:
            if event.isAutoRepeat():
                return
        except Exception:
            pass
        self.pressed_keys.add(event.key())

    def keyReleaseEvent(self, event):
        # track key release; ignore auto-repeat
        try:
            if event.isAutoRepeat():
                return
        except Exception:
            pass
        k = event.key()
        if k in self.pressed_keys:
            self.pressed_keys.remove(k)

    def game_loop(self):
        # move paddles based on pressed keys (supports simultaneous input)
        paddle_speed = 8  # pixels per frame; adjust to taste
        # Player 1 (bottom): Left/Right arrows
        if Qt.Key_Left in self.pressed_keys:
            self.paddle_x -= paddle_speed
        if Qt.Key_Right in self.pressed_keys:
            self.paddle_x += paddle_speed
        # Player 2 (top): A/D keys
        if Qt.Key_A in self.pressed_keys:
            self.paddle2_x -= paddle_speed
        if Qt.Key_D in self.pressed_keys:
            self.paddle2_x += paddle_speed

        # clamp paddles inside widget
        if self.paddle_x < 0:
            self.paddle_x = 0
        if self.paddle_x + self.paddle_width > self.width():
            self.paddle_x = self.width() - self.paddle_width
        if self.paddle2_x < 0:
            self.paddle2_x = 0
        if self.paddle2_x + self.paddle2_width > self.width():
            self.paddle2_x = self.width() - self.paddle2_width

        # move ball
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        r = self.ball_radius
        w, h = self.width(), self.height()

        # collide with left/right walls
        if self.ball_x - r <= 0 or self.ball_x + r >= w:
            self.ball_dx *= -1

        # Paddle collisions
        # Bottom paddle (Player 1)
        if (self.ball_y + r >= self.paddle_y) and (self.ball_y - r <= self.paddle_y + self.paddle_height):
            if (self.paddle_x <= self.ball_x <= self.paddle_x + self.paddle_width):
                self.ball_dy = -abs(self.ball_dy)
                self.ball_y = self.paddle_y - r - 1

        # Top paddle (Player 2)
        if (self.ball_y - r <= self.paddle2_y + self.paddle2_height) and (self.ball_y + r >= self.paddle2_y):
            if (self.paddle2_x <= self.ball_x <= self.paddle2_x + self.paddle2_width):
                self.ball_dy = abs(self.ball_dy)
                self.ball_y = self.paddle2_y + self.paddle2_height + r + 1

        # Scoring: ball passed bottom -> point to top player; ball passed top -> point to bottom player
        if self.ball_y - r > h:
            # ball went below bottom: player2 scores
            self.player2_score += 1
            self._reset_ball(toward_up=False)

            # notify Main (if available) but do not pause the game
            if hasattr(self, 'score_callback') and callable(self.score_callback):
                try:
                    # call the callback to return the current score; Main.main may update speed/paddle when called
                    self.score_callback(player1_score=self.player1_score, player2_score=self.player2_score)
                except Exception:
                    pass

        elif self.ball_y + r < 0:
            # ball went above top: player1 scores
            self.player1_score += 1
            self._reset_ball(toward_up=True)

            # notify Main (if available) but do not pause the game
            if hasattr(self, 'score_callback') and callable(self.score_callback):
                try:
                    self.score_callback(player1_score=self.player1_score, player2_score=self.player2_score)
                except Exception:
                    pass

        self.update()

    def _reset_ball(self, toward_up=True):
        # reset ball to spawn center; set vertical direction
        self.ball_x = self.spawn_x
        self.ball_y = self.spawn_y
        # choose a random launch angle depending on whether the ball should go up or down
        # avoid too-flat angles by selecting between 45 and 135 degrees away from horizontal
        if toward_up:
            # upward: angles between -135deg and -45deg
            angle = random.uniform(-3 * math.pi / 4, -1 * math.pi / 4)
        else:
            # downward: angles between 45deg and 135deg
            angle = random.uniform(math.pi / 4, 3 * math.pi / 4)
        speed = float(self._initial_speed)
        self.ball_dx = speed * math.cos(angle)
        self.ball_dy = speed * math.sin(angle)


if __name__ == "__main__":
    # This part of the code only runs if this file is directly run with python
    script = Main()

    arguments = {
        "Ball speed": 5.0,
        "Paddle size": 120,
    }

    # initialize main with default arguments (keeps Main state consistent)
    values = script.main(**arguments)
    print("Initial Main returned:", values)

    # Try to start the GUI if PySide2 is available
    try:
        import sys
        from PySide2.QtWidgets import QApplication

        app = QApplication(sys.argv)
        widget = PongWidget(speed=arguments["Ball speed"], paddle_size=arguments["Paddle size"])
        # register widget with Main so Main.renew_widget attaches the callback and keeps reference
        script.renew_widget(widget)
        widget.show()
        sys.exit(app.exec_())
    except Exception as e:
        print("Could not start GUI (PySide2 may be missing or failed to initialize):", e)
