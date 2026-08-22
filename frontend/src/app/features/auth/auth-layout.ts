import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Icon } from '../../shared/icon/icon';

/** Split-screen frame shared by the login and signup pages. */
@Component({
  selector: 'app-auth-layout',
  imports: [RouterOutlet, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './auth-layout.html',
  styleUrl: './auth-layout.scss',
})
export class AuthLayout {}
