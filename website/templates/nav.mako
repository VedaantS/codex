<%def name="nav(service_name, service_url, service_support_url)">
<link rel="stylesheet" href='/static/css/nav.css'>
<div class="osf-nav-wrapper" role="navigation">

<nav class="navbar navbar-inverse navbar-fixed-top" id="navbarScope" style="background-color: #0A122A; font-family:Outfit, 'Helvetica', sans-serif; box-shadow: 0px;">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap" rel="stylesheet">
    <div class="container">
        <div class="navbar-header">
        <!-- logo here -->
        <div class="service-name">
            <a href="${service_url}">
                <span class="hidden-xs"> Atlantis | </span>
                <span class="current-service" style="margin-left: 0px;"><strong>CODEX</strong></span>
            </a>
        </div>
        <div class="dropdown primary-nav">
            <button data-bind="click: trackClick.bind($data, 'Dropdown Arrow')" class="dropdown-toggle btn-link" data-toggle="dropdown" aria-expanded="false" aria-label="Toggle primary navigation">
                <span class="fa fa-caret-down fa-2x"></span>
            </button>
            <ul class="dropdown-menu service-dropdown" role="menu">
                <li><a data-bind="click: trackClick.bind($data, 'Home')" href="${domain}">HOME</a></li>
                <li><a data-bind="click: trackClick.bind($data, 'Preprints')" href="${domain}preprints/">PREPRINTS</a></li>
                <li><a data-bind="click: trackClick.bind($data, 'Registries')" href="${domain}registries/">REGISTRIES</a></li>
                <li><a data-bind="click: trackClick.bind($data, 'Meetings')" href="${domain}meetings/">MEETINGS</a></li>
                % if institutional_landing_flag:
                    <li><a data-bind="click: trackClick.bind($data, 'Institutions')" href="${domain}institutions/">INSTITUTIONS</a></li>
                % endif
            </ul>
        </div>
        <button type="button" class="navbar-toggle collapsed" data-toggle="collapse" data-target="#secondary-navigation" aria-label="Toggle secondary navigation"}}>
            <span class="sr-only">Toggle navigation</span>
            <span class="icon-bar"></span>
            <span class="icon-bar"></span>
            <span class="icon-bar"></span>
        </button>
    </div>
    <div id="navbar" class="navbar-collapse collapse navbar-right">
        <ul class="nav navbar-nav"></ul>
    </div><!--/.navbar-collapse -->

    <div class="navbar-collapse collapse navbar-right" id="secondary-navigation">
        <ul class="nav navbar-nav">
            % if service_name == 'HOME':
                % if user_name:
                    <li><a data-bind="click: trackClick.bind($data, 'MyProjects')" href="${domain}myprojects/">My Projects</a></li>
                % endif
                    <li><a id="navbar-search" data-bind="click: trackClick.bind($data, 'Search')" href="${domain}search/">Search</a></li>
            % endif
            <li class="dropdown">
            <a id="navbar-support" data-bind="click: trackClick.bind($data, '${service_name} Support')" href="${service_support_url}">Help</a>
            </li>
            % if user_name and display_name:
            <li class="dropdown secondary-nav-dropdown">
                <a class="dropdown-toggle btn-link" data-toggle="dropdown" role="button" aria-expanded="false" aria-label="Toggle auth dropdown">
                    <div class="osf-profile-image">
                        <img src="${user_profile_image}" alt="User profile image">
                    </div>
                    <div class="nav-profile-name">
                            ${display_name}
                    </div>
                    <div class="caret"></div>
                </a>

                <ul class="dropdown-menu auth-dropdown" role="menu">
                    <li><a data-bind="click: trackClick.bind($data, 'MyProfile')" href="${domain}profile/"><i class="fa fa-user fa-lg p-r-xs"></i> My Profile</a></li>
                    <li><a data-bind="click: trackClick.bind($data, 'Support')" href="https://help.osf.io/" ><i class="fa fa-life-ring fa-lg p-r-xs"></i> OSF Support</a></li>
                    <li><a data-bind="click: trackClick.bind($data, 'Settings')" href="${web_url_for('user_profile')}"><i class="fa fa-cog fa-lg p-r-xs"></i> Settings</a></li>
                    <li><a data-bind="click: trackClick.bind($data, 'Logout')" href="${web_url_for('auth_logout')}"><i class="fa fa-sign-out fa-lg p-r-xs"></i> Log out</a></li>
                </ul>
            </li>
            % elif allow_login:
                %if institution:
                    <li class="dropdown sign-in">
                    <div class="btn-group">
                        <a href="${domain}login/?campaign=institution&next=${redirect_url}">
                            <button type="button" class="btn btn-info btn-top-login">
                            Sign in <span class="hidden-xs"><i class="fa fa-arrow-right"></i></span>
                            </button>
                        </a>
                    </div>
                    </li>
                %else :
                <li class="dropdown sign-in">
                    <div class="col-sm-12">
                        <a data-bind="click: trackClick.bind($data, 'SignUp')" href="${sign_up_url}" class="btn btn-success btn-top-signup m-r-xs">Sign Up</a>
                        <a data-bind="click: trackClick.bind($data, 'SignIn')" href="${login_url}" class="btn btn-info btn-top-login p-sm">Sign In</a>
                    </div>
                </li>
                %endif
            % endif

        </ul>
    </div>
</div>
</nav>
    <div class="container-fluid">
        <div class="row">
            <div class="col">
                ## Maintenance alert
                % if maintenance:
                    <div id="maintenance" class="scripted alert alert-dismissible" role="alert">
                    <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                        <span aria-hidden="true">&times;</span></button>
                    <strong>Notice:</strong>
                    % if maintenance['message']:
                        ${maintenance['message']}
                    % else:
                        The site will undergo maintenance between <span id="maintenanceTime"></span>.
                        Thank you for your patience.
                    % endif
                </div>
                % endif
                ## End Maintenance alert
            </div>
        </div>
    </div>
</div>
</%def>
